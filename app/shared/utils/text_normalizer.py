"""Shared text normalization utilities used before catalog lookup, intent detection and customer-data parsing."""

from __future__ import annotations

import unicodedata
import re


def normalize_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(
        " " if unicodedata.category(ch) == "Cf" else ch
        for ch in decomposed
        if unicodedata.category(ch) != "Mn"
    )
    without_accents = re.sub(r"\bazado\b", "asado", without_accents)
    without_accents = re.sub(r"\bbrostee\b", "broster", without_accents)
    without_accents = re.sub(r"\b(neki|enqui)\b", "nequi", without_accents)
    return " ".join(without_accents.split())
