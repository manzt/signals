# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import typing
from unittest.mock import MagicMock

import pytest

from signals import Signal, computed, effect


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


def test_computed_is_readonly() -> None:
    a = Signal(0)
    b = computed(lambda: a() + 1)
    with pytest.raises(AttributeError):
        b.set(10)


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
