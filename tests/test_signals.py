# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import typing
from unittest.mock import MagicMock

import pytest

from signals import (
    Signal,
    batch,
    computed,
    create_subscriber,
    effect,
    effect_scope,
    untrack,
)

T = typing.TypeVar("T")


def test_signal_return_value() -> None:
    v = [1, 2]
    s = Signal(v)
    assert s() == v
    assert s.get() == v


def test_signal_inheritance() -> None:
    assert isinstance(Signal(0), Signal)


def test_signal_to_string() -> None:
    s = Signal(123)
    assert str(s) == "123"


def test_signal_notifies_other_listeners() -> None:
    s = Signal(0)
    spy1 = MagicMock(side_effect=s)
    spy2 = MagicMock(side_effect=s)
    spy3 = MagicMock(side_effect=s)

    effect(spy1)
    dispose = effect(typing.cast("typing.Callable", spy2))
    effect(spy3)

    assert spy1.call_count == 1
    assert spy2.call_count == 1
    assert spy3.call_count == 1

    dispose()

    s.set(1)
    assert spy1.call_count == 2
    assert spy2.call_count == 1
    assert spy3.call_count == 2

    s.set(20)
    assert spy1.call_count == 3
    assert spy2.call_count == 1
    assert spy3.call_count == 3


def test_signal_peek() -> None:
    s = Signal(1)
    assert s.peek() == 1


def test_signal_peek_after_value_change() -> None:
    s = Signal(1)
    s.set(2)
    assert s.peek() == 2


def test_signal_peek_not_depend_on_surrounding_effect() -> None:
    s = Signal(1)
    spy = MagicMock(s.peek)

    effect(spy)
    assert spy.call_count == 1

    s.set(2)
    assert spy.call_count == 1


def test_basic_computed() -> None:
    a = Signal("hello")
    b = Signal("world")
    c = computed(lambda: f"{a} {b}")

    assert c() == "hello world"

    b.set("foo")
    assert c() == "hello foo"


def test_signal_peek_not_depend_on_surrounding_computed() -> None:
    s = Signal(1)
    spy = MagicMock(s.peek)
    d = computed(spy)

    d()
    assert spy.call_count == 1

    s.set(2)
    d()
    assert spy.call_count == 1


def test_signal_subscribe() -> None:
    spy = MagicMock()
    a = Signal(1)

    a.subscribe(spy)
    assert spy.call_count == 1
    assert spy.call_args[0][0] == 1


def test_signal_subscribe_value_change() -> None:
    spy = MagicMock()
    a = Signal(1)

    a.subscribe(spy)

    a.set(2)
    assert spy.call_count == 2
    assert spy.call_args[0][0] == 2


def test_signal_unsubscribe() -> None:
    spy = MagicMock()
    a = Signal(1)

    dispose = a.subscribe(spy)
    dispose()
    spy.reset_mock()

    a.set(2)
    assert spy.call_count == 0


def test_computed_notifies_listeners() -> None:
    a = Signal(0)
    b = Signal(0)
    c = computed(lambda: a() + b())

    spy = MagicMock(side_effect=c)
    dispose = effect(typing.cast("typing.Callable", spy))
    assert spy.call_count == 1

    a.set(a() + 1)
    a.set(a() + 1)
    assert spy.call_count == 3

    dispose()
    a.set(a() + 1)
    assert spy.call_count == 3


def test_computed_computed() -> None:
    a = Signal(0)
    b = Signal(0)
    c = computed(lambda: a() + b())
    d = computed(lambda: c() * 2)

    assert d() == 0

    a.set(a() + 1)
    b.set(b() + 2)

    assert d() == 6


def test_explicit_dependencies() -> None:
    a = Signal(42)
    b = Signal(35)

    spy = MagicMock()

    @effect(deps=(a, b))
    def _(avalue: int, _bvalue: int) -> None:
        # We want to make sure the effect works even if bv is never accessed
        spy(avalue if True else _bvalue)

    spy.assert_called_once()
    spy.assert_called_with(42)
    spy.reset_mock()
    b.set(10)
    spy.assert_called_once()
    spy.assert_called_with(42)


def test_explicit_dependencies_deferred() -> None:
    a = Signal(42)
    b = Signal(35)

    spy = MagicMock()

    @effect(deps=(a, b), defer=True)
    def _(value: int, bvalue: int) -> None:
        spy(value, bvalue)

    spy.assert_not_called()
    a.set(1)
    spy.assert_called_once_with(1, 35)


def test_propagates_changes_through_computeds() -> None:
    src = Signal(0)
    c1 = computed(lambda: src() % 2)
    c2 = computed(c1)
    c3 = computed(c2)

    c3()
    src.set(1)  # c1 -> dirty, c2 -> toCheckDirty, c3 -> toCheckDirty
    c2()  # c1 -> none, c2 -> none
    src.set(3)  # c1 -> dirty, c2 -> toCheckDirty

    assert c3() == 1


def test_clears_subscriptions_when_untracked_by_all_subscribers() -> None:
    a = Signal(1)
    b = computed(lambda: a() * 2)
    spy = MagicMock(side_effect=b)
    dispose = effect(typing.cast("typing.Callable", spy))

    assert spy.call_count == 1
    a.set(2)
    assert spy.call_count == 2
    dispose()
    a.set(3)
    assert spy.call_count == 2


def test_does_not_run_untracked_inner_effect() -> None:
    a = Signal(3)
    b = computed(lambda: a() > 0)

    @effect
    def _() -> None:
        if b():

            @effect
            def _() -> None:
                if a() == 0:
                    pytest.fail("Should never happen")

    a.set(a() - 1)
    a.set(a() - 1)
    a.set(a() - 1)


def test_runs_outer_effect_first() -> None:
    a = Signal(1)
    b = Signal(1)

    @effect
    def _() -> None:
        if a():

            @effect
            def _() -> None:
                b()
                if a() == 0:
                    pytest.fail("Should not happen")

    with batch():
        b.set(0)
        a.set(0)


def test_does_not_trigger_inner_effect_when_resolve_maybe_dirty() -> None:
    a = Signal(0)
    b = computed(lambda: a() % 2)
    spy = MagicMock()

    @effect
    def _() -> None:
        @effect
        def _() -> None:
            b()
            spy()

    a.set(2)
    assert spy.call_count == 1


def test_triggers_inner_effects_in_sequence() -> None:
    a = Signal(0)
    b = Signal(0)
    c = computed(lambda: a() - b())
    order: list[str] = []

    @effect
    def _() -> None:
        c()

        @effect
        def _() -> None:
            order.append("first inner")
            a()

        @effect
        def _() -> None:
            order.append("last inner")
            a()
            b()

    order.clear()
    with batch():
        b.set(1)
        a.set(1)

    assert order == ["first inner", "last inner"]


def test_custom_batched_effect() -> None:
    def batch_effect(fn: typing.Callable[[], None]) -> typing.Callable[[], None]:
        return effect(lambda: batch(fn))

    logs: list[str] = []
    a = Signal(0)
    b = Signal(0)

    @computed
    def aa() -> None:
        logs.append("aa-0")
        if a() == 0:
            b.set(1)
        logs.append("aa-1")

    @computed
    def bb() -> None:
        logs.append("bb")
        b()

    batch_effect(bb)
    batch_effect(aa)

    assert logs == ["bb", "aa-0", "aa-1", "bb"]


def test_duplicate_subscribers_do_not_affect_notify_order() -> None:
    src1 = Signal(0)
    src2 = Signal(0)
    order: list[str] = []

    @effect
    def _() -> None:
        order.append("a")
        with untrack():
            is_one = src2() == 1
        if is_one:
            src1()
        src2()
        src1()

    @effect
    def _() -> None:
        order.append("b")
        src1()

    src2.set(1)  # src1.subs: a -> b -> a

    order.clear()
    src1.set(src1() + 1)
    assert order == ["a", "b"]


def test_effect_scope() -> None:
    count = Signal(1)
    spy = MagicMock()

    @effect_scope
    def scope() -> None:
        @effect
        def _() -> None:
            spy()
            count()

    assert spy.call_count == 1
    count.set(2)
    assert spy.call_count == 2

    scope()
    count.set(3)
    assert spy.call_count == 2


def test_pause_tracking() -> None:
    src = Signal(0)

    c = computed(lambda: untrack(src))

    assert c() == 0

    src.set(1)
    assert c() == 0


def test_effects_can_have_cleanup() -> None:
    a = Signal(0)
    spy = MagicMock()

    @effect
    def _() -> typing.Callable[[], None]:
        a()
        return spy

    assert spy.call_count == 0

    a.set(10)
    a.set(13)
    assert spy.call_count == 2


def test_create_subscriber() -> None:
    import traitlets  # noqa: PLC0415

    class Foo(traitlets.HasTraits):
        value = traitlets.Int(0)

    foo = Foo()

    def start(update: typing.Callable[[], None]) -> typing.Callable[[], None]:
        foo.observe(update, names="value")
        return lambda: foo.unobserve(update, names="value")

    subscribe = create_subscriber(start)

    history = []

    @effect
    def _() -> None:
        subscribe()
        history.append(foo.value)

    foo.value = 10
    foo.value = 20
    foo.value = 30

    assert history == [0, 10, 20, 30]
