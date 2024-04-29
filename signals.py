"""A signals implementation for Python based on @preact/signals."""

from __future__ import annotations

import typing

__all__ = [
    "signal",
    "computed",
    "effect",
    "untracked",
    "batch",
    "Signal",
    "Computed",
    "Effect",
]

# An named symbol/brand for detecting Signal instances even when they weren't
# created using the same signals library version.
BRAND_SYMBOL = object()

# Flags for Computed and Effect.
RUNNING = 1 << 0
NOTIFIED = 1 << 1
OUTDATED = 1 << 2
DISPOSED = 1 << 3
HAS_ERROR = 1 << 4
TRACKING = 1 << 5


class Node:
    """A linked list node used to track dependencies (sources) and dependents (targets).

    Also used to remember the source's last version number that the target saw.
    """

    __slots__ = [
        "_source",
        "_prev_source",
        "_next_source",
        "_target",
        "_prev_target",
        "_next_target",
        "_version",
        "_rollback_node",
    ]

    def __init__(
        self,
        _source: Signal,
        _prev_source: Node | None,
        _next_source: Node | None,
        _target: Computed | Effect,
        _prev_target: Node | None,
        _next_target: Node | None,
        _version: float,
        _rollback_node: Node | None,
    ):
        # A source whose value the target depends on.
        self._source = _source
        self._prev_source = _prev_source
        self._next_source = _next_source

        # A target that depends on the source and should be notified when the source changes.
        self._target = _target
        self._prev_target = _prev_target
        self._next_target = _next_target

        # The version number of the source that target has last seen. We use version numbers
        # instead of storing the source value, because source values can take arbitrary amount
        # of memory, and computeds could hang on to them forever because they're lazily evaluated.
        # Use the special value -1 to mark potentially unused but recyclable nodes.
        self._version = _version

        # Used to remember & roll back the source's previous `._node` value when entering &
        # exiting a new evaluation context.
        self._rollback_node = _rollback_node


# Effects collected into a batch.
batched_effect: Effect | None = None
batch_depth = 0
batch_iteration = 0

# A global version number for signals, used for fast-pathing repeated
# computed.peek()/computed.value calls when nothing has changed globally.
global_version = 0


def start_batch():
    """Start a batch of effects."""
    global batch_depth
    batch_depth += 1


def end_batch():
    """End a batch of effects."""
    global batch_depth
    global batch_iteration
    global batched_effect

    if batch_depth > 1:
        batch_depth -= 1
        return

    error = None
    has_error = False

    while batched_effect is not None:
        effect = batched_effect
        batched_effect = None
        batch_iteration += 1

        while effect is not None:
            next_effect = effect._next_batched_effect
            effect._next_batched_effect = None
            effect._flags &= ~NOTIFIED

            if not (effect._flags & DISPOSED) and needs_to_recompute(effect):
                try:
                    effect._callback()  # Run the effect's callback
                except Exception as err:
                    if not has_error:
                        error = err
                        has_error = True  # Mark that an error occurred

            effect = next_effect  # Move to the next effect in the batch

    batch_iteration = 0  # Reset batch iteration count
    batch_depth -= 1  # Decrement the batch depth

    if has_error and error is not None:
        # If an error occurred, raise it
        raise error


T = typing.TypeVar("T")


def batch(fn: typing.Callable[[], T]) -> T:
    """
    Combine multiple value updates into one "commit" at the end of the provided callback.

    Batches can be nested, and changes are only flushed once the outermost batch callback completes.
    Accessing a signal that has been modified within a batch will reflect its updated value.

    Parameters
    ----------
    fn : Callable[[], T]
        The callback function to execute within the batch.

    Returns
    -------
    T
        The value returned by the callback function.
    """
    if batch_depth > 0:
        return fn()

    start_batch()
    try:
        return fn()
    finally:
        end_batch()


# Currently evaluated computed or effect.
eval_context: Computed | Effect | None = None


def untracked(fn: typing.Callable[[], T]) -> T:
    """Run a callback function that can access signal values without subscribing to the signal updates.

    Parameters
    ----------
    fn : Callable[[], T]
        The callback function.

    Returns
    -------
    T
        The value returned by the callback.
    """
    global eval_context
    prev_context = eval_context
    eval_context = None
    try:
        return fn()
    finally:
        eval_context = prev_context


def add_dependency(signal: Signal) -> Node | None:
    """Add a dependency to the currently evaluated effect or computed signal."""
    if eval_context is None:
        return None

    node = signal._node

    if node is None or node._target != eval_context:
        #
        # `signal` is a new dependency. Create a new dependency node, and set it
        # as the tail of the current context's dependency list. e.g:
        #
        # { A <-> B       }
        #         ↑     ↑
        #        tail  node (new)
        #               ↓
        # { A <-> B <-> C }
        #               ↑
        #              tail (eval_context._sources)
        node = Node(
            _version=0,
            _source=signal,
            _prev_source=eval_context._sources,
            _next_source=None,
            _target=eval_context,
            _prev_target=None,
            _next_target=None,
            _rollback_node=node,
        )

        if eval_context._sources is not None:
            eval_context._sources._next_source = node

        eval_context._sources = node
        signal._node = node

        # Subscribe to change notifications from this dependency if we're in an effect
        # OR evaluating a computed signal that in turn has subscribers.
        if eval_context._flags & TRACKING:
            signal._subscribe(node)

        return node

    elif node._version == -1:
        # `signal` is an existing dependency from a previous evaluation. Reuse it.
        node._version = 0

        #
        # If `node` is not already the current tail of the dependency list (i.e.
        # there is a next node in the list), then make the `node` the new tail. e.g:
        #
        # { A <-> B <-> C <-> D }
        #         ↑           ↑
        #        node   ┌─── tail (eval_context._sources)
        #         └─────│─────┐
        #               ↓     ↓
        # { A <-> C <-> D <-> B }
        #                     ↑
        #                    tail (eval_context._sources)
        #
        if node._next_source is not None:
            node._next_source._prev_source = node._prev_source

            if node._prev_source is not None:
                node._prev_source._next_source = node._next_source

            node._prev_source = eval_context._sources
            node._next_source = None

            if eval_context._sources:
                eval_context._sources._next_source = node
            eval_context._sources = node

        # We can assume that the currently evaluated effect / computed signal is already
        # subscribed to change notifications from `signal` if needed.
        return node

    return None


# The base class for plain and computed signals
class Signal(typing.Generic[T]):
    """Represents a signal that can be subscribed to for changes in value."""

    __slots__ = ["_value", "_version", "_node", "_targets", "brand"]
    _value: T | None
    _version: int
    _node: Node | None
    _targets: Node | None

    def __init__(self, value: T | None = None):
        self._value = value
        self._version = 0
        self._node = None
        self._targets = None
        self.brand = BRAND_SYMBOL

    def _refresh(self) -> bool:
        return True

    def _subscribe(self, node: Node):
        if self._targets != node and node._prev_target is None:
            node._next_target = self._targets
            if self._targets is not None:
                self._targets._prev_target = node
            self._targets = node

    def _unsubscribe(self, node: Node):
        if self._targets is not None:
            prev = node._prev_target
            next = node._next_target
            if prev is not None:
                prev._next_target = next
                node._prev_target = None
            if next is not None:
                next._prev_target = prev
                node._next_target = None
            if node == self._targets:
                self._targets = next

    def subscribe(
        self, fn: typing.Callable[[T], typing.Any]
    ) -> typing.Callable[[], None]:
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
        return effect(lambda: fn(self.value))

    def __repr__(self) -> str:
        return f"Signal({self.value})"

    def __str__(self) -> str:
        """Return the string representation of the signal's value."""
        return str(self.value)

    def peek(self) -> T:
        """Get the current value of the signal without subscribing to changes."""
        return self.value

    @property
    def value(self) -> T:
        """Get the current value of the signal."""
        node = add_dependency(self)
        if node is not None:
            node._version = self._version
        return self._value  # type: ignore

    @value.setter
    def value(self, value: T):
        global global_version
        global batch_iteration

        if value != self._value:
            if batch_iteration > 100:
                raise RuntimeError("Cycle detected")

            self._value = value
            self._version += 1
            global_version += 1

            start_batch()
            try:
                node = self._targets
                while node is not None:
                    node._target._notify()
                    node = node._next_target
            finally:
                end_batch()


def signal(value: T) -> Signal[T]:
    """Create a new plain signal.

    Parameters
    ----------
    value : T
        The initial value for the signal.
    """
    return Signal(value)


def needs_to_recompute(target: Computed | Effect) -> bool:
    """Determine if a computed signal needs to recompute its value."""
    # Check the dependencies for changed values. The dependency list is already
    # in order of use. Therefore if multiple dependencies have changed values, only
    # the first used dependency is re-evaluated at this point.
    node = target._sources
    while node is not None:
        # If there's a new version of the dependency before or after refreshing,
        # or the dependency has something blocking it from refreshing at all,
        # then recomputation is required.
        if (
            node._source._version != node._version
            or not node._source._refresh()
            or node._source._version != node._version
        ):
            return True

        node = node._next_source

    # If none of the dependencies have changed values, recomputation is not required.
    return False


def prepare_sources(target: Computed | Effect) -> None:
    """Prepare sources for a target in a doubly linked list.

    1. Mark all current sources as reusable nodes (version: -1).
    2. Set a rollback node if the current node is used in a different context.
    3. Point 'target._sources' to the tail of the doubly-linked list.
    """
    node = target._sources
    while node is not None:
        rollback_node = node._source._node
        if rollback_node is not None:
            node._rollback_node = rollback_node

        node._source._node = node
        node._version = -1
        if node._next_source is None:
            target._sources = node
            break

        node = node._next_source


def cleanup_sources(target: Computed | Effect) -> None:
    """Clean up sources for a target in a doubly linked list."""
    node = target._sources
    head: Node | None = None

    """
    At this point, 'target._sources' points to the tail of the doubly-linked list.
    It contains all existing sources and new sources in order of use.
    Iterate backward until we find the head node while dropping old dependencies.
    """
    while node is not None:
        prev = node._prev_source

        # If the node was not reused, unsubscribe from change notifications and remove from the list.
        if node._version == -1:
            node._source._unsubscribe(node)

            if prev is not None:
                prev._next_source = node._next_source

            if node._next_source is not None:
                node._next_source._prev_source = prev
        else:
            # The new head is the last node that wasn't removed/unsubscribed from the list.
            head = node

        # Restore the node's previous context and clear the rollback node if it was set.
        node._source._node = node._rollback_node
        if node._rollback_node is not None:
            node._rollback_node = None

        node = prev  # Move backward through the list

    # Update the target's sources to the head node.
    target._sources = head


class Computed(Signal[T]):
    """Represents a signal whose value is derived from other signals."""

    __slots__ = ["_fn", "_sources", "_global_version", "_flags"]

    _fn: typing.Callable[[], T]
    _sources: Node | None
    _global_version: int
    _flags: int

    def __init__(self, fn: typing.Callable[[], T]):
        super().__init__(None)
        self._fn = fn
        self._sources = None
        self._global_version = global_version - 1
        self._flags = OUTDATED

    def _refresh(self) -> bool:
        global eval_context

        self._flags &= ~NOTIFIED

        if self._flags & RUNNING:
            return False

        # If this computed signal has subscribed to updates from its dependencies
        # (TRACKING flag set) and none of them have notified about changes (OUTDATED
        # flag not set), then the computed value can't have changed.
        if (self._flags & (OUTDATED | TRACKING)) == TRACKING:
            return True

        self._flags &= ~OUTDATED

        if self._global_version == global_version:
            return False

        self._global_version = global_version

        # Mark this computed signal running before checking the dependencies for value
        # changes, so that the RUNNING flag can be used to notice cyclical dependencies.
        self._flags |= RUNNING
        if self._version > 0 and not needs_to_recompute(self):
            self._flags &= ~RUNNING
            return True

        prev_context = eval_context
        try:
            prepare_sources(self)
            eval_context = self
            value = self._fn()
            if self._flags & HAS_ERROR or self._value != value or self._version == 0:
                self._value = value
                self._version += 1
                self._flags &= ~HAS_ERROR
        except Exception as err:
            self._value = err  # type: ignore
            self._flags |= HAS_ERROR
            self._version += 1
        eval_context = prev_context
        cleanup_sources(self)
        self._flags &= ~RUNNING
        return True

    def _subscribe(self, node: Node | None):
        if self._targets is None:
            self._flags |= OUTDATED | TRACKING

            node = self._sources
            while node is not None:
                node._source._subscribe(node)
                node = node._next_source

        if node:
            super()._subscribe(node)

    def _unsubscribe(self, node: Node | None):
        if self._targets is not None:
            if node:
                super()._unsubscribe(node)

            if self._targets is None:
                self._flags &= ~TRACKING
                node = self._sources
                while node is not None:
                    node._source._unsubscribe(node)
                    node = node._next_source

    def _notify(self):
        if not (self._flags & NOTIFIED):
            self._flags |= OUTDATED | NOTIFIED
            node = self._targets
            while node is not None:
                node._target._notify()
                node = node._next_target

    @property
    def value(self) -> T:
        if self._flags & RUNNING:
            raise RuntimeError("Cycle detected")

        node = add_dependency(self)
        self._refresh()

        if node is not None:
            node._version = self._version

        if self._flags & HAS_ERROR:
            raise typing.cast(Exception, self._value)

        return self._value  # type: ignore

    @value.setter
    def value(self, value: T):
        raise AttributeError("Computed signals are read-only")

    def __repr__(self) -> str:
        return f"ReadonlySignal({self.value})"


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


def cleanup_effect(effect: Effect) -> None:
    """Run cleanup functions for an effect."""
    global eval_context
    cleanup = effect._cleanup
    effect._cleanup = None
    if callable(cleanup):
        start_batch()
        # Run cleanup functions always outside of any context.
        prev_context = eval_context
        eval_context = None
        try:
            cleanup()
        except Exception as err:
            effect._flags &= ~RUNNING
            effect._flags |= DISPOSED
            dispose_effect(effect)
            raise err
        finally:
            eval_context = prev_context
            end_batch()


def dispose_effect(effect: Effect) -> None:
    """Dispose an effect."""
    node = effect._sources
    while node is not None:
        node._source._unsubscribe(node)
        node = node._next_source

    effect._fn = None
    effect._sources = None

    cleanup_effect(effect)


def end_effect(self: Effect, prev_context: Computed | Effect | None = None):
    """End the evaluation of an effect."""
    global eval_context
    if eval_context != self:
        raise RuntimeError("Out-of-order effect")

    cleanup_sources(self)
    eval_context = prev_context

    self._flags &= ~RUNNING

    if self._flags & DISPOSED:
        dispose_effect(self)

    end_batch()


CleanupFn = typing.Callable[[], None]
EffectFn = typing.Callable[[], None | CleanupFn]


class Effect:
    """Represents a side-effect that runs in response to signal changes."""

    __slots__ = ["_fn", "_cleanup", "_sources", "_next_batched_effect", "_flags"]

    _fn: EffectFn | None
    _cleanup: CleanupFn | None
    _sources: Node | None
    _next_batched_effect: Effect | None
    _flags: int

    def __init__(self, fn: EffectFn | None):
        self._fn = fn
        self._cleanup = None
        self._sources = None
        self._next_batched_effect = None
        self._flags = TRACKING

    def _callback(self):
        finish = self._start()
        try:
            if self._flags & DISPOSED or self._fn is None:
                return

            cleanup = self._fn()
            if callable(cleanup):
                self._cleanup = cleanup
        finally:
            finish()

    def _start(self):
        global eval_context
        if self._flags & RUNNING:
            raise RuntimeError("Cycle detected")

        self._flags |= RUNNING
        self._flags &= ~DISPOSED
        cleanup_effect(self)
        prepare_sources(self)

        start_batch()  # Inline the start batch
        prev_context = eval_context
        eval_context = self

        return lambda: end_effect(self, prev_context)

    def _notify(self):
        global batched_effect
        if not (self._flags & NOTIFIED):
            self._flags |= NOTIFIED
            self._next_batched_effect = batched_effect
            batched_effect = self

    def _dispose(self):
        self._flags |= DISPOSED

        if not (self._flags & RUNNING):
            dispose_effect(self)


def effect(fn: EffectFn | None) -> typing.Callable[[], None]:
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
    effect_instance = Effect(fn)
    try:
        effect_instance._callback()
    except Exception as err:
        effect_instance._dispose()
        raise err

    return effect_instance._dispose
