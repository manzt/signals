# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


def test_anywidget_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anywidget", None)
    with pytest.raises(ImportError) as excinfo:
        import signals.inputs  # noqa: F401, PLC0415

    assert "anywidget is required" in str(excinfo.value)


def test_anywidget_installed() -> None:
    import signals.inputs  # noqa: F401, PLC0415


def test_input_subscribe() -> None:
    from signals.inputs import Input  # noqa: PLC0415

    inp = Input(1, label=None, disabled=False)
    spy = MagicMock()

    dispose = inp.subscribe(spy)
    assert spy.call_count == 1
    assert spy.call_args[0][0] == 1

    inp.set(2)
    assert spy.call_count == 2
    assert spy.call_args[0][0] == 2

    dispose()
    inp.set(3)
    assert spy.call_count == 2


def test_input_subscribe_defer() -> None:
    from signals.inputs import Input  # noqa: PLC0415

    inp = Input(1, label=None, disabled=False)
    spy = MagicMock()

    dispose = inp.subscribe(spy, defer=True)
    assert spy.call_count == 0

    inp.set(2)
    assert spy.call_count == 1
    assert spy.call_args[0][0] == 2

    dispose()
    inp.set(3)
    assert spy.call_count == 1
