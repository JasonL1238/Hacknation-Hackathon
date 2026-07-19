"""Inline SVG icon set for BioShield AI (Lucide-style, stroke-based).

Per the UI/UX design guidance we use vector icons rather than emoji so glyphs
render consistently across platforms and inherit theme colors via currentColor.
"""

from __future__ import annotations

# 24×24 viewBox path bodies, stroke = currentColor.
_PATHS = {
    # Brand: shield (firewall/defensive) with a check.
    "shield-check": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6'
        'a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5'
        'a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>'
    ),
    # Verdicts
    "x-circle": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "minus-circle": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
    # Evidence categories
    "bar-chart": '<path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-4"/>',
    "circle": '<circle cx="12" cy="12" r="10"/>',
    # Feedback / misc
    "alert-triangle": (
        '<path d="m10.29 3.86-8.4 14.53A2 2 0 0 0 3.6 21h16.8a2 2 0 0 0 1.73-3L13.71 3.86'
        'a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>'
    ),
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "flask": (
        '<path d="M9 3h6"/><path d="M10 3v6.5L4.7 18a2 2 0 0 0 1.7 3h11.2a2 2 0 0 0 1.7-3'
        'L14 9.5V3"/><path d="M7.5 15h9"/>'
    ),
}


def icon(name: str, size: int = 20, stroke: float = 2, cls: str = "") -> str:
    """Return an inline SVG string for `name`, inheriting color via currentColor."""
    body = _PATHS.get(name, "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" class="gf-ico {cls}" '
        f'style="display:inline-block;vertical-align:-0.15em;flex:none">{body}</svg>'
    )
