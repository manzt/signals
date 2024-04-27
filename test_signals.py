from unittest.mock import MagicMock

from signals import Signal, computed, effect, signal


def test_signal_return_value():
    v = [1, 2]
    s = signal(v)
    assert s.value == v


def test_signal_inherits_from_Signal():
    assert isinstance(signal(0), Signal)


def test_signal_to_string():
    s = signal(123)
    assert str(s) == "123"


def test_signal_notifies_other_listeners():
    s = signal(0)
    spy1 = MagicMock(lambda: s.value)
    spy2 = MagicMock(lambda: s.value)
    spy3 = MagicMock(lambda: s.value)

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


def test_signal_peek():
    s = signal(1)
    assert s.peek() == 1


def test_signal_peek_after_value_change():
    s = signal(1)
    s.value = 2
    assert s.peek() == 2


def test_signal_peek_not_depend_on_surrounding_effect():
    s = signal(1)
    spy = MagicMock(lambda: s.peek())

    effect(spy)
    assert spy.call_count == 1

    s.value = 2
    assert spy.call_count == 1


def test_signal_peek_not_depend_on_surrounding_computed():
    s = signal(1)
    spy = MagicMock(lambda: s.peek())
    d = computed(spy)

    d.value
    assert spy.call_count == 1

    s.value = 2
    d.value
    assert spy.call_count == 1


def test_signal_subscribe():
    spy = MagicMock()
    a = signal(1)

    a.subscribe(spy)
    assert spy.call_count == 1
    assert spy.call_args[0][0] == 1


def test_signal_subscribe_value_change():
    spy = MagicMock()
    a = signal(1)

    a.subscribe(spy)

    a.value = 2
    assert spy.call_count == 2
    assert spy.call_args[0][0] == 2


def test_signal_unsubscribe():
    spy = MagicMock()
    a = signal(1)

    dispose = a.subscribe(spy)
    dispose()
    spy.reset_mock()

    a.value = 2
    assert spy.call_count == 0


def test_signal_subscription_not_trigger_on_callback_signal_change():
    spy = MagicMock()
    a = signal(0)
    b = signal(0)

    a.subscribe(lambda: b.value and spy())
    assert spy.call_count == 1
    spy.reset_mock()

    b.value += 1
    assert spy.call_count == 0


def test_signal_no_cause_surrounding_effect_to_subscribe_on_signal_change():
    spy = MagicMock()
    a = signal(0)
    b = signal(0)

    effect(lambda: a.subscribe(lambda: b.value and spy()))
    assert spy.call_count == 1
    spy.reset_mock()

    b.value += 1
    assert spy.call_count == 0
