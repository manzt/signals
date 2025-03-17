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

__all__ = ["Signal", "computed", "context", "effect", "effect_scope"]


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
        if context.active_sub:
            system.link(self, context.active_sub)
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
                system.propagate(self.subs)
                if not context.batch_depth:
                    system.process_effect_notifications()

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

    def subscribe(self, fn: typing.Callable[[T], None]) -> Disposer:
        """Subscribe to changes in the signal.

        Parameters
        ----------
        fn : Callable[[T], None]
            The callback function to run when the signal changes.

        Returns
        -------
        Callable[[], None]
            A function for unsubscribing from the signal.
        """
        return effect(lambda: fn(self()))


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
            system.process_computed_update(
                typing.cast("DependencyWithSubscriber", self), self.flags
            )
        if context.active_sub:
            system.link(self, context.active_sub)
        elif context.active_scope:
            system.link(self, context.active_scope)
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

    @contextlib.contextmanager
    def batch(self) -> typing.Generator[None, None, None]:
        """Combine multiple updates into one "commit".

        Nested batches are supported, and changes take effect immediately, but
        notifications are suppressed until batching completes.

        Yields
        ------
        None
        """
        self.batch_depth += 1
        try:
            yield
        finally:
            self.batch_depth -= 1
            if self.batch_depth <= 0:
                system.process_effect_notifications()

    @contextlib.contextmanager
    def pause_tracking(self) -> typing.Generator[None, None, None]:
        """Temporarily disable tracking, restoring the previous state on exit."""
        self.pause_stack.append(self.active_sub)
        self.active_sub = None
        try:
            yield
        finally:
            self.active_sub = self.pause_stack.pop()


def update_computed(computed: Computed) -> bool:
    prev_sub = context.active_sub
    context.active_sub = computed
    system.start_tracking(computed)
    try:
        new_value = computed.getter()
        if computed.current != new_value:
            computed.current = new_value
            return True
        return False
    finally:
        context.active_sub = prev_sub
        system.end_tracking(computed)


def run_effect(e: Effect) -> None:
    if e.cleanup:
        e.cleanup()
    e.cleanup = None

    prev_sub = context.active_sub
    context.active_sub = e
    system.start_tracking(e)
    try:
        result = e.fn()
        if callable(result):
            e.cleanup = result
    finally:
        context.active_sub = prev_sub
        system.end_tracking(e)


def run_effect_scope(e: EffectScope, fn: typing.Callable[[], T]) -> T:
    prev_sub = context.active_scope
    context.active_scope = e
    system.start_tracking(e)
    try:
        return fn()
    finally:
        context.active_scope = prev_sub
        system.end_tracking(e)


def notify_effect(e: Effect | EffectScope) -> bool:
    if isinstance(e, EffectScope):
        return notify_effect_scope(e)

    flags = e.flags
    if flags & SubscriberFlags.Dirty or (
        flags & SubscriberFlags.PendingComputed and system.update_dirty_flag(e, flags)
    ):
        run_effect(e)
    else:
        system.process_pending_inner_effects(e, e.flags)

    return True


def notify_effect_scope(e: EffectScope) -> bool:
    flags = e.flags
    if flags & SubscriberFlags.PendingEffect:
        system.process_pending_inner_effects(e, e.flags)
        return True
    return False


def create_disposer(sub: Effect | EffectScope) -> Disposer:
    def dispose() -> None:
        if isinstance(sub, Effect) and sub.cleanup:
            sub.cleanup()
        system.start_tracking(sub)
        system.end_tracking(sub)

    return dispose


context = ReactiveContext()
system = ReactiveSystem(update_computed=update_computed, notify_effect=notify_effect)  # type: ignore  # noqa: PGH003


def _effect(fn: typing.Callable[[], Disposer | None]) -> Disposer:
    e = Effect(fn)
    if context.active_sub:
        system.link(e, context.active_sub)
    elif context.active_scope:
        system.link(e, context.active_scope)
    run_effect(e)
    return create_disposer(e)


@typing.overload
def effect(  # noqa: D418
    deps: typing.Sequence[Signal],
    *,
    defer: bool = False,
) -> typing.Callable[[typing.Callable[..., Disposer | None]], Disposer]:
    """Create an effect with explicit dependencies.

    An effect is a side-effect that runs in response to signal changes.

    Parameters
    ----------
    deps : Sequence[Signal]
        The signals that the effect depends on.

    defer : bool, optional
        Defer the effect until the next change, rather than running immediately.
        By default, False.

    Returns
    -------
    Callable[[Callable[..., None]], Disposer]
        A decorator function for creating effects.
    """


@typing.overload
def effect(fn: typing.Callable[[], Disposer | None], /) -> Disposer:  # noqa: D418
    """Create an effect to run arbitrary code in response to signal changes.

    An effect tracks which signals are accessed within the given callback
    function `fn`, and re-runs the callback when those signals change.

    The callback may return a cleanup function. The cleanup function gets
    run once, either when the callback is next called or when the effect
    gets disposed, whichever happens first.

    Parameters
    ----------
    fn : Callable[[], None]
        The effect callback.

    Returns
    -------
    Callable[[], None]
        A function for disposing the effect.
    """


def effect(*args, **kwargs) -> typing.Callable:
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
    """Run a function in an isolated effect scope and return a disposer.

    Effects inside the scope track dependencies and react to changes.
    Calling the disposer stops reactivity.

    Parameters
    ----------
    fn : Callable[[], T]
        A function containing reactive computations.

    Returns
    -------
    Disposer
        A callable that, when invoked, disposes of the effect scope.

    Example
    -------
    >>> count = Signal(1)
    >>> logs = []
    >>>
    >>> scope = effect_scope(lambda: effect(lambda: logs.append(count())))
    >>> count.set(2)
    >>> assert logs == [1, 2]  # Effect runs on change
    >>> scope()  # Dispose of the effect scope
    >>> count.set(3)
    >>> assert logs == [1, 2]  # No further reactions
    """
    e = EffectScope()
    run_effect_scope(e, fn)
    return create_disposer(e)


def computed(fn: typing.Callable[[], T]) -> Computed[T]:
    """Create a new signal that is computed based on the values of other signals.

    The returned computed signal is read-only, and its value is automatically
    updated when any signals accessed from within the callback function change.

    Parameters
    ----------
    fn : Callable[[], T]
        The function to compute the value of the signal.

    Returns
    -------
    Computed[T]
        A new read-only signal.
    """
    return Computed(fn)
