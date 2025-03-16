# Adapted from preact-signals at https://github.com/preactjs/signals/blob/main/packages/core/test/signal.test.tsx
#
# The MIT License (MIT)
#
# Copyright (c) 2022-present Preact Team
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from signals import Signal, computed, effect


def test__should_drop_a_b_a_updates() -> None:
    #     A
    #   / |
    #  B  |
    #   \ |
    #     C
    #     |
    #     D
    a = Signal(2)
    b = computed(lambda: a() - 1)
    c = computed(lambda: a() + b())

    compute = MagicMock(side_effect=lambda: f"d: {c()}")

    d = computed(compute)
    # Trigger read
    assert d() == "d: 3"
    compute.assert_called_once()
    compute.reset_mock()

    a.set(4)
    d()
    compute.assert_called_once()


def test_only_updates_every_signal_once_for_diamond_graph() -> None:
    # In this scenario "D" should only update once when "A" receives
    # an update. This is sometimes referred to as the "diamond" scenario.
    #    A
    #  /   \
    # B     C
    #  \   /
    #    D

    a = Signal("a")
    b = computed(a)
    c = computed(a)

    spy = MagicMock(side_effect=lambda: f"{b()} {c()}")
    d = computed(spy)

    assert d() == "a a"
    assert spy.call_count == 1
    a.set("aa")
    assert d() == "aa aa"
    assert spy.call_count == 2


def test_only_updates_every_signal_once_for_diamond_graph_with_tail() -> None:
    # "E" will be likely updated twice if our mark+sweep logic is buggy.
    #     A
    #   /   \
    #  B     C
    #   \   /
    #     D
    #     |
    #     E

    a = Signal("a")
    b = computed(a)
    c = computed(a)

    d = computed(lambda: b() + " " + c())

    spy = MagicMock(side_effect=d)
    e = computed(spy)

    assert e() == "a a"
    assert spy.call_count == 1
    a.set("aa")
    assert e() == "aa aa"
    assert spy.call_count == 2


def test_bails_out_if_result_is_the_same() -> None:
    # Bail out if value of "B" never changes
    # A->B->C
    a = Signal("a")

    @computed
    def b() -> str:
        a()
        return "foo"

    spy = MagicMock(side_effect=b)
    c = computed(spy)

    assert c() == "foo"
    assert spy.call_count == 1
    a.set("aa")
    assert c() == "foo"
    assert spy.call_count == 1


def test_only_updates_every_signal_once_for_jagged_diamond_graph_with_tails() -> None:
    # "F" and "G" will be likely updated twice if our mark+sweep logic is buggy.
    #    A
    #  /   \
    # B     C
    # |     |
    # |     D
    #  \   /
    #    E
    #  /   \
    # F     G
    a = Signal("a")
    b = computed(a)
    c = computed(a)
    d = computed(c)
    call_order: list[str] = []

    e_spy = MagicMock(side_effect=lambda: f"{b()} {d()}")

    @computed
    def e() -> str:
        call_order.append("e")
        return e_spy()

    f_spy = MagicMock(side_effect=e)

    @computed
    def f() -> str:
        call_order.append("f")
        return f_spy()

    g_spy = MagicMock(side_effect=e)

    @computed
    def g() -> str:
        call_order.append("g")
        return g_spy()

    assert f() == "a a"
    assert f_spy.call_count == 1

    assert g() == "a a"
    assert g_spy.call_count == 1

    e_spy.reset_mock()
    f_spy.reset_mock()
    g_spy.reset_mock()
    call_order.clear()

    a.set("b")

    assert e() == "b b"
    assert e_spy.call_count == 1

    assert f() == "b b"
    assert f_spy.call_count == 1

    assert g() == "b b"
    assert g_spy.call_count == 1

    e_spy.reset_mock()
    f_spy.reset_mock()
    g_spy.reset_mock()
    call_order.clear()

    a.set("c")

    assert e() == "c c"
    assert e_spy.call_count == 1

    assert f() == "c c"
    assert f_spy.call_count == 1

    assert g() == "c c"
    assert g_spy.call_count == 1

    assert call_order == ["e", "f", "g"]


def test_only_subscribes_to_signals_listened_to_a() -> None:
    #    *A
    #   /   \
    # *B     C <- we don't listen to C
    a = Signal("a")

    b = computed(a)
    spy = MagicMock(side_effect=a)
    computed(spy)
    assert b() == "a"
    assert not spy.called

    a.set("aa")
    assert b() == "aa"
    assert not spy.called


def test_only_subscribes_to_signals_listened_to_b() -> None:
    # Here both "B" and "C" are active in the beginning, but
    # "B" becomes inactive later. At that point it should
    # not receive any updates anymore.
    #    *A
    #   /   \
    # *B     D <- we don't listen to C
    #  |
    # *C
    a = Signal("a")
    b_spy = MagicMock(side_effect=a)
    b = computed(b_spy)

    c_spy = MagicMock(side_effect=b)
    c = computed(c_spy)

    d = computed(a)

    result = ""

    @effect
    def unsub() -> None:
        nonlocal result
        result = c()

    assert result == "a"
    assert d() == "a"

    b_spy.reset_mock()
    c_spy.reset_mock()
    unsub()

    a.set("aa")

    assert not b_spy.called
    assert not c_spy.called
    assert d() == "aa"


def test_ensures_subs_update_even_if_one_dep_unmarks_it() -> None:
    # In this scenario "C" always returns the same value. When "A"
    # changes, "B" will update, then "C" at which point its update
    # to "D" will be unmarked. But "D" must still update because
    # "B" marked it. If "D" isn't updated, then we have a bug.
    #     A
    #   /   \
    #  B     *C <- returns same value every time
    #   \   /
    #     D
    a = Signal("a")
    b = computed(a)

    @computed
    def c() -> str:
        a()
        return "c"

    return_values = []

    def d_impl() -> str:
        return_values.append(f"{b()} {c()}")
        return return_values[-1]

    spy = MagicMock(side_effect=d_impl)
    d = computed(spy)
    assert d() == "a c"
    spy.reset_mock()
    return_values.clear()
    a.set("aa")
    d()
    assert spy.call_count == 1
    assert return_values[0] == "aa c"


def test_subs_update_even_if_two_deps_unmark_it() -> None:
    # In this scenario both "C" and "D" always return the same
    # value. But "E" must still update because "A" marked it.
    # If "E" isn't updated, then we have a bug.
    #     A
    #   / | \
    #  B *C *D
    #   \ | /
    #     E
    a = Signal("a")
    b = computed(a)

    @computed
    def c() -> str:
        a()
        return "c"

    @computed
    def d() -> str:
        a()
        return "d"

    return_values: list[str] = []

    def e_impl() -> str:
        return_values.append(f"{b()} {c()} {d()}")
        return return_values[-1]

    spy = MagicMock(side_effect=e_impl)
    e = computed(spy)

    assert e() == "a c d"
    spy.reset_mock()
    return_values.clear()
    a.set("aa")
    e()
    assert spy.call_count == 1
    assert return_values[0] == "aa c d"


def test_supports_lazy_branches() -> None:
    a = Signal(0)
    b = computed(a)
    c = computed(lambda: a() if a() > 0 else b())

    assert c() == 0
    a.set(1)
    assert c() == 1
    a.set(0)
    assert c() == 0


def test_does_not_update_a_sub_if_all_deps_unmark_it() -> None:
    # In this scenario "B" and "C" always return the same value. When "A"
    # changes, "D" should not update.
    #     A
    #   /   \
    # *B     *C
    #   \   /
    #     D
    a = Signal("a")

    @computed
    def b() -> str:
        a()
        return "b"

    @computed
    def c() -> str:
        a()
        return "c"

    spy = MagicMock(side_effect=lambda: f"{b()} {c()}")
    d = computed(spy)
    assert d() == "b c"
    spy.reset_mock()
    a.set("aa")
    assert not spy.called


def test_keeps_graph_consistent_on_errors_during_activation() -> None:
    a = Signal(0)

    @computed
    def b() -> None:
        msg = "fail"
        raise ValueError(msg)

    c = computed(a)

    with pytest.raises(ValueError, match="fail"):
        b()

    a.set(1)
    assert c() == 1


def test_keeps_graph_consistent_on_errors_in_computeds() -> None:
    a = Signal(0)

    @computed
    def b() -> int:
        if a() == 1:
            msg = "fail"
            raise ValueError(msg)
        return a()

    c = computed(b)

    assert c() == 0

    a.set(1)
    with pytest.raises(ValueError, match="fail"):
        b()

    a.set(2)
    assert c() == 2
