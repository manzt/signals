# Copyright (c) 2024 Trevor Manz
"""Primitives for transparent reactive programming in Python."""

from __future__ import annotations

from ._core import (
    Signal,
    batch,
    computed,
    create_subscriber,
    effect,
    effect_scope,
    untrack,
)
from ._version import __version__


def load_ipython_extension(ipython) -> None:  # noqa: ANN001
    """Load the IPython extension.

    `%load_ext signals` will load the extension and enable the `%%effect` cell magic.

    Parameters
    ----------
    ipython : IPython.core.interactiveshell.InteractiveShell
        The IPython shell instance.
    """
    from ._cellmagic import load_ipython_extension  # noqa: PLC0415

    load_ipython_extension(ipython)
