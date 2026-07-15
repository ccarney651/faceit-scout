"""Shared exception types, in their own module so any module can import them
without creating an import cycle."""

from __future__ import annotations


class CaptureError(RuntimeError):
    """A capture/runtime problem: no backend available, a missing dependency,
    a resolution mismatch, an empty selection, etc. Surfaced to the operator as
    a clean ``error: ...`` message, never a traceback."""
