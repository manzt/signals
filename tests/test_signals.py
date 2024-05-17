from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from signals import Signal, computed, effect


def test_signal_return_value():
    v = [1, 2]
    s = Signal(v)
    assert s.value == v


def test_signal_inherits_from_Signal():
    assert isinstance(Signal(0), Signal)


def test_signal_to_string():
    s = Signal(123)
    assert str(s) == "123"


def test_signal_notifies_other_listeners():
    s = Signal(0)
    spy1 = MagicMock(side_effect=lambda: s.value)
    spy2 = MagicMock(side_effect=lambda: s.value)
    spy3 = MagicMock(side_effect=lambda: s.value)

    effect(spy1)
    dispose = effect(spy2)
    effect(spy3)

    assert spy1.call_count == 1
    assert spy2.call_count == 1
    assert spy3.call_count == 1

    dispose()

    s.value = 1
    assert spy1.call_count == 2
    assert spy2.call_count == 1
    assert spy3.call_count == 2

    s.value = 20
    assert spy1.call_count == 3
    assert spy2.call_count == 1
    assert spy3.call_count == 3


def test_signal_peek():
    s = Signal(1)
    assert s.peek() == 1


def test_signal_peek_after_value_change():
    s = Signal(1)
    s.value = 2
    assert s.peek() == 2


def test_signal_peek_not_depend_on_surrounding_effect():
    s = Signal(1)
    spy = MagicMock(s.peek)

    effect(spy)
    assert spy.call_count == 1

    s.value = 2
    assert spy.call_count == 1


def test_basic_computed():
    a = Signal("hello")
    b = Signal("world")
    c = computed(lambda: f"{a} {b}")

    assert c.value == "hello world"

    b.value = "foo"
    assert c.value == "hello foo"


def test_computed_is_readonly():
    a = Signal(0)
    b = computed(lambda: a.value + 1)
    with pytest.raises(AttributeError):
        b.value = 10


def test_signal_peek_not_depend_on_surrounding_computed():
    s = Signal(1)
    spy = MagicMock(s.peek)
    d = computed(spy)

    d.value  # noqa: B018
    assert spy.call_count == 1

    s.value = 2
    d.value  # noqa: B018
    assert spy.call_count == 1


def test_signal_subscribe():
    spy = MagicMock()
    a = Signal(1)

    a.subscribe(spy)
    assert spy.call_count == 1
    assert spy.call_args[0][0] == 1


def test_signal_subscribe_value_change():
    spy = MagicMock()
    a = Signal(1)

    a.subscribe(spy)

    a.value = 2
    assert spy.call_count == 2
    assert spy.call_args[0][0] == 2


def test_signal_unsubscribe():
    spy = MagicMock()
    a = Signal(1)

    dispose = a.subscribe(spy)
    dispose()
    spy.reset_mock()

    a.value = 2
    assert spy.call_count == 0


def test_computed_notifies_listeners():
    a = Signal(0)
    b = Signal(0)
    c = computed(lambda: a.value + b.value)

    spy = MagicMock(side_effect=lambda: c.value)
    dispose = effect(spy)
    assert spy.call_count == 1

    a.value += 1
    a.value += 1
    assert spy.call_count == 3

    dispose()
    a.value += 1
    assert spy.call_count == 3


def test_computed_computed():
    a = Signal(0)
    b = Signal(0)
    c = computed(lambda: a.value + b.value)
    d = computed(lambda: c.value * 2)

    assert d.value == 0

    a.value += 1
    b.value += 2

    assert d.value == 6


def test_explicit_dependencies():
    a = Signal(42)
    b = Signal(35)

    spy = MagicMock()

    @effect(deps=(a, b))
    def _(av, _):
        # We want to make sure the effect works even if bv is never accessed
        spy(av if True else _)

    spy.assert_called_once()
    spy.assert_called_with(42)
    spy.reset_mock()
    b.value = 10
    spy.assert_called_once()
    spy.assert_called_with(42)


def test_explicit_dependencies_deferred():
    a = Signal(42)
    b = Signal(35)

    spy = MagicMock()

    @effect(deps=(a, b), defer=True)
    def _(av, bv):
        spy(av, bv)

    spy.assert_not_called()
    a.value = 1
    spy.assert_called_once_with(1, 35)
