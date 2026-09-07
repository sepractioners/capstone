"""Deterministic contract-profile retrieval with a future vector-RAG seam."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROFILE_DIR = Path(__file__).with_name("profiles")


def _load_profiles() -> list[dict[str, Any]]:
    profiles = []
    for path in PROFILE_DIR.glob("*.yaml"):
        with path.open(encoding="utf-8") as profile_file:
            profiles.append(yaml.safe_load(profile_file))
    return profiles


PROFILES = _load_profiles()


def retrieve_profile(source_uri: str, first_page_text: str = "") -> dict[str, Any]:
    """Select the best fallback profile from document text only.

    This is intentionally deterministic. A vector retriever can replace this
    function later while preserving its result shape and trace contract.
    """
    haystack = first_page_text.lower()
    candidates = [profile for profile in PROFILES if profile["id"] != "unclassified"]
    scored = [
        (sum(keyword.lower() in haystack for keyword in profile.get("keywords", [])), profile)
        for profile in candidates
    ]
    score, profile = max(
        scored,
        key=lambda item: item[0],
        default=(0, next(p for p in PROFILES if p["id"] == "unclassified")),
    )
    if score <= 0:
        profile = next(p for p in PROFILES if p["id"] == "unclassified")
    return {
        "id": profile["id"],
        "name": profile["name"],
        "score": score,
        "required_fields": profile.get("required_fields", []),
        "recommended_fields": profile.get("recommended_fields", []),
        "retrieval_mode": "deterministic_profile",
        "vector_enabled": False,
    }
