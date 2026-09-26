"""Garage label helper (FAKE FIXTURE, lesson 005)."""


def garage_label(name: str) -> str:
    """Return the Garage label exactly as the Garage shows it: strip spaces, keep the Я glyph and casing."""
    return name.strip().upper()


def is_numbered(label: str) -> bool:
    """Naming law: bots are never shown as ЯBOT#N."""
    return "#" in label
