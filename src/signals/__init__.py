import importlib.metadata

from ._signals import Signal, batch, computed, effect  # noqa: F401

__version__ = importlib.metadata.version("signals")
