"""A signals implementation for Python."""

import importlib.metadata

from ._signals import Signal, batch, computed, effect  # noqa: F401

__version__ = importlib.metadata.version("signals")


def load_ipython_extension(ipython):
    """Load the IPython extension."""
    from ._cellmagic import load_ipython_extension

    load_ipython_extension(ipython)
