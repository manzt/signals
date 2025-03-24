# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import contextlib
import enum
import typing

from ._system import (
    Dependency,
    DependencyWithSubscriber,
    ReactiveSystem,
    Subscriber,
    SubscriberFlags,
)

__all__ = [
    "Signal",
    "batch",
    "computed",
    "create_subscriber",
    "effect",
    "effect_scope",
    "untrack",
]


T = typing.TypeVar("T")

Disposer = typing.Callable[[], None]


class Signal(Dependency, typing.Generic[T]):
    """Represents a time-varying value."""

    def __init__(self, value: T) -> None:
        self.current = value
        self.subs = None
        self.subs_tail = None

    def peek(self) -> T:
        """Get the current value of the signal without subscribing to changes.

        Returns
        -------
        T
            The current value of the signal.
        """
        return self.current

    def get(self) -> T:
        """Get the current value of the signal.

        Returns
        -------
        T
            The current value of the signal.
        """
        if CONTEXT.active_sub:
            SYSTEM.link(self, CONTEXT.active_sub)
        return self.current

    def set(self, update: T) -> None:
        """Set the value of the signal.

        Parameters
        ----------
        update : T
            The new value of the signal.
        """
        if self.current != update:
            self.current = update
            if self.subs:
                SYSTEM.propagate(self.subs)
                if not CONTEXT.batch_depth:
                    SYSTEM.process_effect_notifications()

    def __call__(self) -> T:
        """Get the current value of the signal.

        An alias for the `get` method.

        Returns
        -------
        T
            The current value of the signal.
        """
        return self.get()

    def __str__(self) -> str:
        return str(self())

    def __repr__(self) -> str:
        return f"Signal({self()})"

    def subscribe(
        self, fn: typing.Callable[[T], None], *, defer: bool = False
    ) -> Disposer:
        """Subscribe to changes in the signal.

        Parameters
        ----------
        fn : Callable[[T], None]
            The callback function to run when the signal changes.
        defer : bool, optional
            If `True`, defers execution until the first change. Defaults to `False`.

        Returns
        -------
        Callable[[], None]
            A function for unsubscribing from the signal.
        """
        return effect(deps=(self,), defer=defer)(fn)


class UnsetType(enum.Enum):
    UNSET = "UNSET"


class Computed(Dependency, Subscriber, typing.Generic[T]):
    """Represents a signal whose value is derived from other signals."""

    def __init__(self, getter: typing.Callable[[], T]) -> None:
        self.current: UnsetType | T = UnsetType.UNSET
        self.subs = None
        self.subs_tail = None
        self.deps = None
        self.deps_tail = None
        self.flags = SubscriberFlags.Computed | SubscriberFlags.Dirty
        self.getter = getter

    def peek(self) -> T | UnsetType:
        """Get the current value of the computed without subscribing to changes.

        If there are no subscriptions, the intial value is `UnsetType`.

        Returns
        -------
        T | UnsetType
            The current value of the computed.
        """
        return self.current

    def get(self) -> T:
        """Get the current value of the computed.

        Returns
        -------
        T
            The current value of the computed.
        """
        if self.flags and (SubscriberFlags.Dirty | SubscriberFlags.PendingComputed):
            SYSTEM.process_computed_update(
                typing.cast("DependencyWithSubscriber", self), self.flags
            )
        if CONTEXT.active_sub:
            SYSTEM.link(self, CONTEXT.active_sub)
        elif CONTEXT.active_scope:
            SYSTEM.link(self, CONTEXT.active_scope)
        return typing.cast("T", self.current)

    def __call__(self) -> T:
        """Get the current value of the computed.

        Returns
        -------
        T
            The current value of the computed.
        """
        return self.get()

    def __str__(self) -> str:
        return str(self())

    def __repr__(self) -> str:
        return f"Computed({self()})"


class Effect(Dependency, Subscriber):
    """Represents a side-effect that runs in response to signal changes."""

    def __init__(self, fn: typing.Callable[[], Disposer | None]) -> None:
        self.fn = fn
        self.cleanup: Disposer | None = None
        self.subs = None
        self.subs_tail = None
        self.deps = None
        self.deps_tail = None
        self.flags = SubscriberFlags.Effect

    def __repr__(self) -> str:
        return "Effect()"


class EffectScope(Subscriber):
    """Represents a disposable scope for running effects."""

    def __init__(self) -> None:
        self.deps = None
        self.deps_tail = None
        self.flags = SubscriberFlags.Effect

    def __repr__(self) -> str:
        return "EffectScope()"


class ReactiveContext:
    """Represents the global context of push-pull based reactivity system."""

    def __init__(self) -> None:
        self.batch_depth = 0
        self.pause_stack: list[Subscriber | None] = []
        self.active_sub: Subscriber | None = None
        self.active_scope: EffectScope | None = None


def update_computed(computed: Computed) -> bool:
    prev_sub = CONTEXT.active_sub
    CONTEXT.active_sub = computed
    SYSTEM.start_tracking(computed)
    try:
        new_value = computed.getter()
        if computed.current != new_value:
            computed.current = new_value
            return True
        return False
    finally:
        CONTEXT.active_sub = prev_sub
        SYSTEM.end_tracking(computed)


def run_effect(e: Effect) -> None:
    if e.cleanup:
        e.cleanup()
    e.cleanup = None

    prev_sub = CONTEXT.active_sub
    CONTEXT.active_sub = e
    SYSTEM.start_tracking(e)
    try:
        result = e.fn()
        if callable(result):
            e.cleanup = result
    finally:
        CONTEXT.active_sub = prev_sub
        SYSTEM.end_tracking(e)


def run_effect_scope(e: EffectScope, fn: typing.Callable[[], T]) -> T:
    prev_sub = CONTEXT.active_scope
    CONTEXT.active_scope = e
    SYSTEM.start_tracking(e)
    try:
        return fn()
    finally:
        CONTEXT.active_scope = prev_sub
        SYSTEM.end_tracking(e)


def notify_effect(e: Effect | EffectScope) -> bool:
    if isinstance(e, EffectScope):
        return notify_effect_scope(e)

    flags = e.flags
    if flags & SubscriberFlags.Dirty or (
        flags & SubscriberFlags.PendingComputed and SYSTEM.update_dirty_flag(e, flags)
    ):
        run_effect(e)
    else:
        SYSTEM.process_pending_inner_effects(e, e.flags)

    return True


def notify_effect_scope(e: EffectScope) -> bool:
    flags = e.flags
    if flags & SubscriberFlags.PendingEffect:
        SYSTEM.process_pending_inner_effects(e, e.flags)
        return True
    return False


def create_disposer(sub: Effect | EffectScope) -> Disposer:
    def dispose() -> None:
        if isinstance(sub, Effect) and sub.cleanup:
            sub.cleanup()
        SYSTEM.start_tracking(sub)
        SYSTEM.end_tracking(sub)

    return dispose


@contextlib.contextmanager
def _batch() -> typing.Generator[None, None, None]:
    """Combine multiple updates into one "commit"."""
    CONTEXT.batch_depth += 1
    try:
        yield
    finally:
        CONTEXT.batch_depth -= 1
        if CONTEXT.batch_depth <= 0:
            SYSTEM.process_effect_notifications()


@contextlib.contextmanager
def _untrack() -> typing.Generator[None, None, None]:
    """Temporarily disable tracking, restoring the previous state on exit."""
    CONTEXT.pause_stack.append(CONTEXT.active_sub)
    CONTEXT.active_sub = None
    try:
        yield
    finally:
        CONTEXT.active_sub = CONTEXT.pause_stack.pop()


def _effect(fn: typing.Callable[[], Disposer | None]) -> Disposer:
    e = Effect(fn)
    if CONTEXT.active_sub:
        SYSTEM.link(e, CONTEXT.active_sub)
    elif CONTEXT.active_scope:
        SYSTEM.link(e, CONTEXT.active_scope)
    run_effect(e)
    return create_disposer(e)


CONTEXT = ReactiveContext()
SYSTEM = ReactiveSystem(update_computed=update_computed, notify_effect=notify_effect)  # type: ignore  # noqa: PGH003


# Public API


@typing.overload
def batch() -> contextlib._GeneratorContextManager[None, None, None]:
    pass


@typing.overload
def batch(
    fn: typing.Callable[[], T],
) -> T:
    pass


def batch(
    fn: typing.Callable[[], T] | None = None,
) -> contextlib._GeneratorContextManager[None, None, None] | T:
    """Combine multiple updates into one "commit".

    Ensures multiple updates are grouped together, reducing redundant
    notifications until batching completes.

    Can be used either as a context manager or as a function wrapper.

    Nested batches are supported. Changes take effect immediately, but
    notifications are suppressed until all active batch contexts exit.

    Parameters
    ----------
    fn : typing.Callable[[], None], optional
        A function to be executed within the batch.

    Returns
    -------
    None | contextlib._GeneratorContextManager[None, None, None]
        - Returns a context manager when called without arguments.
        - Returns `None` when used as a function wrapper.

    Examples
    --------
    Using `batch` as a context manager:

    >>> with batch():
    >>>     update_1()
    >>>     update_2()  # Notifications are suppressed until the block exits.

    Using `batch` as a function wrapper:

    >>> batch(lambda: update_1())  # Runs `update_1()` within a batch.

    """
    if fn is None:
        return _batch()
    with _batch():
        return fn()


foo = batch(lambda: 10)


@typing.overload
def untrack() -> contextlib._GeneratorContextManager[None, None, None]:
    pass


@typing.overload
def untrack(
    fn: typing.Callable[[], T],
) -> T:
    pass


def untrack(
    fn: typing.Callable[[], T] | None = None,
) -> contextlib._GeneratorContextManager[None, None, None] | T:
    """Ignore tracking any of the dependencies in the executing code block.

    When used inside a `computed` or `effect`, any state read inside `fn`
    will NOT be treated as a dependency.

    Parameters
    ----------
    fn : typing.Callable[[], None], optional
        A function to be executed with tracking disabled.

    Returns
    -------
    None | contextlib._GeneratorContextManager[None, None, None]
        - Returns a context manager when called without arguments.
        - Returns `None` when used as a function wrapper.
    """
    if fn is None:
        return _untrack()
    with _untrack():
        return fn()


@typing.overload
def effect(
    deps: typing.Sequence[Signal],
    *,
    defer: bool = False,
) -> typing.Callable[[typing.Callable[..., Disposer | None]], Disposer]:
    pass


@typing.overload
def effect(fn: typing.Callable[[], Disposer | None], /) -> Disposer:
    pass


def effect(*args, **kwargs) -> typing.Callable:
    """Create a reactive effect.

    Effects are functions that run whenever state updates. When `signals`
    runs an effect function, it tracks which pieces of state (and derived state)
    are accessed (unless accessed inside `untrack`), and re-runs the function
    when that state later changes.

    Effects run **immediately** in order to track dependencies. To instead opt
    in to running the computation only on change, specify explicit dependencies
    with `effect(deps=[...], defer=True)` (See examples).

    The `fn` may return a cleanup function. The cleanup function gets
    run once, either when the callback is next called or when the effect
    gets disposed, whichever happens first.

    Parameters
    ----------
    fn : Callable[[], None | () -> None]
        The function to run in a tracking scope. It MAY return a "cleanup" function,
        which run once, either when `fn` is next called or when the effect gets
        disposed, whichever happens first.

    deps: Sequence[Signal]
        A list of signals for explicit dependency tracking.

    defer : bool, optional
        If `True`, defers execution until the first change. Defaults to `False`.
        Must be used with `deps`.

    Returns
    -------
        - A disposer function (`effect(fn)`).
        - A decorator when using explicit dependencies (`effect(deps=[...])`).

    Examples
    --------
    Basic Usage:

    >>> a = Signal(10)
    >>> effect(lambda: print(a()))
    10
    >>> a.set(20)
    20

    As a Decorator:

    >>> a = Signal(10)
    >>> b = Signal(3)
    >>> @effect
    >>> def _():
    >>>     print(a() + b())
    13
    >>> a.set(20)
    23

    Explicit Dependencies (Immediate):

    >>> a = Signal("a")
    >>> b = Signal("b")
    >>> @effect(deps=[a, b])
    >>> def _(a_val: str, b_val: str):
    >>>     print(f"{a_val} {b_val}")
    "a b"
    >>> a.set("aa")
    "aa b"

    Explicit Dependencies (Lazy):

    >>> a = Signal("a")
    >>> @effect(deps=[a], defer=True)
    >>> def _(a_val: str):
    >>>     print(a_val)
    >>> a.set("aa")
    "aa"

    With Cleanup:

    >>> a = Signal(10)
    >>> def fn():
    >>>     print(a())
    >>>     return lambda: print("Cleanup")
    >>> dispose = effect(fn)
    10
    >>> a.set(20)
    Cleanup
    20
    >>> dispose()  # Manually dispose
    >>> a.set(42)  # No output (effect is disposed)
    """
    if len(args) == 1 and callable(args[0]):
        return _effect(args[0])  # type: ignore  # noqa: PGH003

    deps = args[0] if len(args) == 1 else kwargs.get("deps", [])
    defer = kwargs.get("defer", False)

    def wrap(fn: typing.Callable[[], Disposer | None]) -> Disposer:
        return _effect(on(deps=deps, defer=defer)(fn))

    return wrap


def on(
    deps: typing.Sequence[Signal],
    *,
    defer: bool = False,
) -> typing.Callable[
    [typing.Callable[..., Disposer | None]], typing.Callable[[], Disposer | None]
]:
    """Make dependencies for a function explicit.

    This is an internal utility. Please use `signals.effect` overload instead.

    Parameters
    ----------
    deps : Sequence[Signal]
        The signals that the effect depends on.

    defer : bool, optional
        Defer the effect until the next change, rather than running immediately.
        By default, False.

    Returns
    -------
    Callable[[Callable[..., None]], Callable[[], None]]
        A callback function that can be registered as an effect.

    Examples
    --------
    >>> a = Signal("a")
    >>> @effect
    >>> @on(deps=(a,))
    >>> def _(a: str):
    >>>     print(a.upper())
    "A"
    """

    def decorator(
        fn: typing.Callable[..., Disposer | None],
    ) -> typing.Callable[[], Disposer | None]:
        # The main effect function that will be run.
        def main() -> Disposer | None:
            return fn(*(dep() for dep in deps))

        func = main

        if defer:
            # Create a void function that accesses all of the
            # dependencies so they will be tracked in an effect.
            def void() -> None:
                nonlocal func
                for dep in deps:
                    dep()
                func = main

            func = void

        return lambda: func()  # noqa: PLW0108

    return decorator


def effect_scope(fn: typing.Callable[[], T]) -> Disposer:
    """Create an isolated effect scope.

    Returns a stop function that disposes of all effects registered in the scope.
    Useful for managing the lifecycle of reactive computations.

    Parameters
    ----------
    fn : Callable[[], T]
        A function containing reactive computations.

    Returns
    -------
    Callable[[], None]
        A function that stops the effect scope and prevents further reactivity.

    Example
    -------
    >>> count = Signal(1)
    >>> logs = []
    >>>
    >>> stop = effect_scope(lambda: effect(lambda: logs.append(count())))
    >>> count.set(2)
    >>> assert logs == [1, 2]  # Effect runs on change
    >>> stop()  # Stop the effect scope
    >>> count.set(3)
    >>> assert logs == [1, 2]  # No further reactions
    """
    e = EffectScope()
    run_effect_scope(e, fn)
    return create_disposer(e)


def computed(fn: typing.Callable[[], T]) -> Computed[T]:
    """Derive a read-only signal from others.

    The computed value is determined by `fn`, which accesses other signals.
    It updates whenever those signals change.

    Computeds are **lazy**. They only recalculate when accessed. Peeking
    their value (e.g., `x.peek()`) returns `UnsetType` if not previously
    read (e.g., `x()`).

    Parameters
    ----------
    fn : Callable[[], T]
        A function that computes the value based on other signals.

    Returns
    -------
    Computed[T]
        A new read-only signal.

    Example
    -------
    >>> a = Signal(2)
    >>> b = Signal(3)
    >>> product = computed(lambda: a() * b())

    >>> product()
    6

    >>> a.set(4)
    >>> product()
    12
    """
    return Computed(fn)


def create_subscriber(
    start: typing.Callable[
        [typing.Callable[[], None]], typing.Callable[[], None] | None
    ],
) -> typing.Callable[[], None]:
    """Create a subscriber function that manages an observable effect.

    When `update` is called, the effect re-runs.
    If `start` returns a function, it runs when the effect is destroyed.
    If `subscribe` is used in multiple effects, `start` is only called **once**
    while active, and cleanup runs **once** after all effects are destroyed.

    This function can be useful to hook other event-based APIs, such as
    `traitlets` (see example), into the signals reactivity system.

    Parameters
    ----------
    start : Callable[[Callable[[], None]], Callable[[], None] | None]
        A function that starts listening and returns an optional cleanup function.

    Returns
    -------
    Callable[[], None]
        A function to be called inside an effect to track changes.

    Examples
    --------
    Integrating with `traitlets`

    >>> import traitlets

    >>> class Foo(traitlets.HasTraits):
    >>>     value = traitlets.Int(0)

    >>> foo = Foo()

    >>> def start(update):
    >>>     foo.observe(update, names="value") # Subscribe to changes
    >>>     return lambda: foo.unobserve(update, names="value") # Cleanup when unsubscribed

    >>> subscribe = create_subscriber(start)

    >>> @effect
    >>> def _():
    >>>     subscribe()  # Subscribe to `foo.value` changes
    >>>     print(f"Current value is: {foo.value}")

    >>> foo.value = 42
    "Current value is: 42"
    """  # noqa: E501
    version = Signal(0)
    subscribers = 0
    stop: typing.Callable[[], None] | None = None

    def subscribe() -> None:
        version.get()

        @effect
        def _() -> Disposer:
            nonlocal subscribers, stop

            if subscribers == 0:
                stop = untrack(
                    lambda: start(
                        lambda *_args, **_kwargs: version.set(version.get() + 1)
                    )
                )

            subscribers += 1

            def cleanup() -> None:
                nonlocal subscribers, stop
                subscribers -= 1
                if subscribers == 0 and stop:
                    stop()
                    stop = None

            return cleanup

    return subscribe
