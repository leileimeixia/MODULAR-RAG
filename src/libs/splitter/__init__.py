"""Splitter abstractions."""

from .base_splitter import BaseSplitter, SplitResult
from .splitter_factory import SplitterFactory, SplitterFactoryError

__all__ = [
    "BaseSplitter",
    "SplitResult",
    "SplitterFactory",
    "SplitterFactoryError",
]
