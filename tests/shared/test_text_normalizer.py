"""Automated test module. It documents expected behavior and protects production bot flows from regressions."""

from __future__ import annotations

from app.shared.utils.text_normalizer import normalize_text


def test_normalize_text_removes_accents_and_extra_spaces() -> None:
    assert normalize_text("  Cañaveral   /   FLORIDA  ") == "canaveral / florida"


def test_normalize_text_handles_empty_values() -> None:
    assert normalize_text(None) == ""

