"""Shared text normalization utilities used before catalog lookup, intent detection and customer-data parsing."""

from __future__ import annotations

import unicodedata


def normalize_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.split())

