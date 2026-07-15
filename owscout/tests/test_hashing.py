"""Perceptual-hash Hamming distance — the pure half of the matcher's ref logic."""

from __future__ import annotations

import pytest

from owscout.refs import hamming_hex


def test_identical_hashes_zero_distance() -> None:
    assert hamming_hex("ffff0000ffff0000", "ffff0000ffff0000") == 0


def test_single_bit_difference() -> None:
    assert hamming_hex("0000000000000000", "0000000000000001") == 1


def test_all_bits_differ() -> None:
    assert hamming_hex("0" * 16, "f" * 16) == 64


def test_symmetric() -> None:
    a, b = "a1b2c3d4e5f60718", "1234567890abcdef"
    assert hamming_hex(a, b) == hamming_hex(b, a)


def test_width_mismatch_rejected() -> None:
    with pytest.raises(ValueError):
        hamming_hex("ffff", "ffffffff")
