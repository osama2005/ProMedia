"""Colour palettes used by the whole application.

Every palette exposes light and dark variants.  Values are stored as
``(light, dark)`` tuples so CustomTkinter can switch appearance mode live
without rebuilding a single widget.

Seven palettes come from the Color Hunt links requested for the settings
screen; ``blue`` is the original application palette.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PALETTE = "forest"

# Semantic colours stay identical across palettes so a completed download is
# always green and an error is always red.
_STATUS_LIGHT = {
    "success": "#12A96B",
    "danger": "#D64B54",
    "warn": "#C27318",
}
_STATUS_DARK = {
    "success": "#3FCB87",
    "danger": "#E87979",
    "warn": "#F3A531",
}


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _hex(colour: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(channel))):02X}" for channel in colour)


def _mix(first: str, second: str, ratio: float) -> str:
    """Blend two hex colours; ``ratio`` is how much of *second* to use."""
    ratio = max(0.0, min(1.0, ratio))
    a = _rgb(first)
    b = _rgb(second)
    return _hex(tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3)))  # type: ignore[arg-type]


@dataclass(frozen=True)
class Palette:
    key: str
    preview: tuple[str, str, str, str]
    light: dict[str, str]
    dark: dict[str, str]


def _derive(mode: str, base: dict[str, str]) -> dict[str, str]:
    """Fill the remaining tokens from the eight base colours of a palette."""
    contrast = "#000000" if mode == "light" else "#FFFFFF"
    # Premium depth: subtle borders and soft elevation instead of heavy
    # gradients or glossy effects.  Dark surfaces use slightly quieter mixes
    # so the interface stays calm rather than washed out.
    dark = mode == "dark"
    card = base["card"]
    border = _mix(card, contrast, 0.10 if dark else 0.12)
    row_bg = _mix(card, contrast, 0.03 if dark else 0.04)
    row_border = _mix(card, contrast, 0.09 if dark else 0.11)
    soft_button = _mix(card, contrast, 0.05 if dark else 0.06)
    # Enhanced depth tokens
    card_shadow = _mix(card, contrast, 0.20 if dark else 0.25)
    card_elevated = _mix(card, contrast, 0.12 if dark else 0.15)
    tokens = {
        **base,
        "border": border,
        "sidebar_border": _mix(base["sidebar"], contrast, 0.12),
        "soft_button": soft_button,
        "soft_hover": _mix(soft_button, base["accent"], 0.14 if dark else 0.18),
        "row_bg": row_bg,
        "row_border": row_border,
        "row_hover": _mix(row_border, base["accent"], 0.35 if dark else 0.45),
        "card_soft": _mix(card, base["bg"], 0.55),
        "card_shadow": card_shadow,       # Enhanced shadow token
        "card_elevated": card_elevated,   # Elevated card background
        "shimmer": _mix(card, contrast, 0.09),
        "overlay": "#000000",
        "toast_bg": card,
        "on_accent": "#FFFFFF",
        "success": _STATUS_LIGHT["success"] if mode == "light" else _STATUS_DARK["success"],
        "danger": _STATUS_LIGHT["danger"] if mode == "light" else _STATUS_DARK["danger"],
        "warn": _STATUS_LIGHT["warn"] if mode == "light" else _STATUS_DARK["warn"],
    }
    return tokens


def _base(
    *,
    bg: str,
    card: str,
    sidebar: str,
    muted: str,
    accent: str,
    accent_hover: str,
    accent_soft: str,
    soft_text: str,
) -> dict[str, str]:
    return {
        "bg": bg,
        "card": card,
        "sidebar": sidebar,
        "muted": muted,
        "accent": accent,
        "accent_hover": accent_hover,
        "accent_soft": accent_soft,
        "soft_text": soft_text,
    }


_SPECS: tuple[tuple[str, tuple[str, str, str, str], dict[str, str], dict[str, str]], ...] = (
    (
        "blue",
        ("#2563EB", "#3B82F6", "#DBEAFE", "#F4F5F7"),
        _base(
            bg="#F4F5F7", card="#FFFFFF", sidebar="#FFFFFF", muted="#667085",
            accent="#2563EB", accent_hover="#1D4ED8", accent_soft="#DBEAFE",
            soft_text="#344054",
        ),
        _base(
            bg="#0E0E12", card="#17171C", sidebar="#121216", muted="#98A2B3",
            accent="#3B82F6", accent_hover="#2563EB", accent_soft="#1E293B",
            soft_text="#D0D5DD",
        ),
    ),
    (
        "sand",
        ("#EBEBD8", "#637545", "#455230", "#9BA685"),
        _base(
            bg="#F3F3E8", card="#FFFFFF", sidebar="#EBEBD8", muted="#6F7563",
            accent="#637545", accent_hover="#455230", accent_soft="#E4E8D6",
            soft_text="#3A4032",
        ),
        _base(
            bg="#15170F", card="#20241A", sidebar="#1B1E14", muted="#A6AD98",
            accent="#6F8349", accent_hover="#83995C", accent_soft="#2C3322",
            soft_text="#E1E4D6",
        ),
    ),
    (
        "olive",
        ("#28301C", "#323D25", "#9A7E3B", "#D2CF9A"),
        _base(
            bg="#F4F3EA", card="#FFFFFF", sidebar="#EFEDE0", muted="#6E7160",
            accent="#8A6F2F", accent_hover="#6E5824", accent_soft="#E7E3C9",
            soft_text="#3A3D2C",
        ),
        _base(
            bg="#12150D", card="#1B1F14", sidebar="#171B10", muted="#A3A78F",
            accent="#9A7E3B", accent_hover="#B3964E", accent_soft="#2C3220",
            soft_text="#E4E6D5",
        ),
    ),
    (
        "ocean",
        ("#071B2B", "#167D8D", "#B9E4E8", "#EEEEEE"),
        _base(
            bg="#F1F5F6", card="#FFFFFF", sidebar="#E7F1F3", muted="#5D7379",
            accent="#146F7D", accent_hover="#0F5A65", accent_soft="#D8EEF1",
            soft_text="#274246",
        ),
        _base(
            bg="#071B2B", card="#0D2436", sidebar="#0A2030", muted="#93AEBA",
            accent="#2E9DB0", accent_hover="#45B2C4", accent_soft="#12384A",
            soft_text="#DCEAEF",
        ),
    ),
    (
        "forest",
        ("#0A1510", "#5E8C6A", "#79A985", "#C8D9C6"),
        _base(
            bg="#F3F5F0", card="#FFFFFF", sidebar="#EAEFE8", muted="#66766C",
            accent="#2F5C3E", accent_hover="#244A32", accent_soft="#DDE8DC",
            soft_text="#2E4035",
        ),
        _base(
            bg="#0A1510", card="#12231A", sidebar="#0E1C15", muted="#94A79A",
            accent="#5E8C6A", accent_hover="#79A985", accent_soft="#1D3527",
            soft_text="#E5EBE3",
        ),
    ),
    (
        "sky",
        ("#1B365D", "#005A9C", "#60C1E5", "#A0E0EF"),
        _base(
            bg="#F1F6FA", card="#FFFFFF", sidebar="#E8F1F9", muted="#5E7186",
            accent="#005A9C", accent_hover="#004A80", accent_soft="#D9ECF8",
            soft_text="#23384D",
        ),
        _base(
            bg="#0C1B2B", card="#12273B", sidebar="#0F2233", muted="#94AABB",
            accent="#2E7FBF", accent_hover="#4795D2", accent_soft="#163A55",
            soft_text="#DBE8F2",
        ),
    ),
    (
        "lime",
        ("#15370D", "#728E6D", "#E5CD82", "#FFF2B4"),
        _base(
            bg="#F7F6EC", card="#FFFFFF", sidebar="#F0F1E1", muted="#6E7566",
            accent="#5E7A59", accent_hover="#4A6346", accent_soft="#E9EDD6",
            soft_text="#33402D",
        ),
        _base(
            bg="#111A0D", card="#1B2716", sidebar="#162013", muted="#A5B49D",
            accent="#6F8A4D", accent_hover="#84A061", accent_soft="#2A3A22",
            soft_text="#E6EDDD",
        ),
    ),
    (
        "linen",
        ("#EBE2CC", "#DED6C1", "#CFC6B1", "#B7B09E"),
        _base(
            bg="#F4EFE4", card="#FFFFFF", sidebar="#EBE2CC", muted="#78715F",
            accent="#756C57", accent_hover="#5D5542", accent_soft="#E8E2D2",
            soft_text="#3F3A2E",
        ),
        _base(
            bg="#171510", card="#211F18", sidebar="#1B1913", muted="#A9A291",
            accent="#857B65", accent_hover="#9C917A", accent_soft="#2E2B22",
            soft_text="#E9E3D4",
        ),
    ),
)

PALETTES: dict[str, Palette] = {
    key: Palette(
        key=key,
        preview=preview,
        light=_derive("light", light),
        dark=_derive("dark", dark),
    )
    for key, preview, light, dark in _SPECS
}

PALETTE_KEYS: tuple[str, ...] = tuple(PALETTES)


def tokens(key: str) -> dict[str, tuple[str, str]]:
    """Return every palette token as a ``(light, dark)`` tuple."""
    palette = PALETTES.get(key) or PALETTES[DEFAULT_PALETTE]
    return {
        name: (palette.light[name], palette.dark[name])
        for name in palette.light
    }


def preview_colours(key: str) -> tuple[str, str, str, str]:
    return (PALETTES.get(key) or PALETTES[DEFAULT_PALETTE]).preview
