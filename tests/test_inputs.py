# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import sys

import pytest


def test_anywidget_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anywidget", None)
    with pytest.raises(ImportError) as excinfo:
        import signals.inputs  # noqa: F401, PLC0415

    assert "anywidget is required" in str(excinfo.value)


def test_anywidget_installed() -> None:
    import signals.inputs  # noqa: F401, PLC0415
