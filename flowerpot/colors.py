"""Named colors and hex parsing for the 3MF / preview exports.

Colors have no effect on the geometry - they ride along in the .3mf file
(most slicers pick them up and show the pot in that color) and tint the
preview renders.
"""

from __future__ import annotations

#: Built-in palette.  Any #RGB / #RRGGBB hex value works too.
PALETTE: dict[str, str] = {
    "terracotta": "#C1683C",
    "clay": "#A65B38",
    "white": "#F2EFEA",
    "black": "#2B2B2B",
    "charcoal": "#3C4048",
    "sage": "#9CAF88",
    "olive": "#7A7A52",
    "teal": "#2E7F86",
    "cobalt": "#2B4C9B",
    "sand": "#D9C7A7",
    "blush": "#E8A0BF",
    "mustard": "#D9A521",
}


def parse_color(value: str) -> str:
    """Normalise a palette name or hex string to ``#RRGGBB`` (uppercase).

    Raises ``ValueError`` for anything that is neither.
    """
    v = value.strip().lower()
    if v in PALETTE:
        return PALETTE[v]
    if v.startswith("#"):
        digits = v[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        if len(digits) == 6 and all(c in "0123456789abcdef" for c in digits):
            return "#" + digits.upper()
    raise ValueError(
        f"unknown color {value!r}: use a hex value like #B06040 or one of "
        + ", ".join(sorted(PALETTE))
    )


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """``#RRGGBB`` -> (r, g, b) floats in [0, 1] for the preview renderer."""
    h = parse_color(hex_color).lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
