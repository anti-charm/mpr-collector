from __future__ import annotations

# Subtle professional palettes.  Each uses a three-stop banner gradient and
# layered card/table tones instead of one flat application color.
COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "Warm Clay": {
        "bg": "#f3eee8", "card": "#fbf8f4", "border": "#d8c9bc",
        "text": "#342f2b", "muted": "#756b63", "accent": "#a7644c",
        "accent_hover": "#b87960", "accent_pressed": "#8e533f",
        "soft": "#eee3d8", "soft_hover": "#e5d5c7", "select_bg": "#ead8ca",
        "table_alt": "#edf2f4", "rename_bg": "#f8eddb", "entry_bg": "#fffdfb",
        "shadow": "#e4d8cd", "gradient_start": "#f9f4ed",
        "gradient_middle": "#efddcf", "gradient_end": "#dcc0ae",
        "gradient_text": "#332c28", "gradient_subtext": "#665b54",
    },
    "Sage & Linen": {
        "bg": "#f0f1eb", "card": "#faf9f4", "border": "#cbd0c0",
        "text": "#30352f", "muted": "#687066", "accent": "#657b67",
        "accent_hover": "#758d77", "accent_pressed": "#536657",
        "soft": "#e3e7dc", "soft_hover": "#d9dfd1", "select_bg": "#d9e3d6",
        "table_alt": "#f0f3ee", "rename_bg": "#f4ead5", "entry_bg": "#fffef9",
        "shadow": "#d8dccc", "gradient_start": "#fbf8ef",
        "gradient_middle": "#e3e7d6", "gradient_end": "#becab6",
        "gradient_text": "#30362f", "gradient_subtext": "#646d62",
    },
    "Slate & Sky": {
        "bg": "#eef1f3", "card": "#f8fafb", "border": "#c7d0d6",
        "text": "#2d3439", "muted": "#66727a", "accent": "#58758b",
        "accent_hover": "#6a879c", "accent_pressed": "#466276",
        "soft": "#dfe7eb", "soft_hover": "#d4dfe5", "select_bg": "#d6e3eb",
        "table_alt": "#eef4f7", "rename_bg": "#f5ead6", "entry_bg": "#fcfdfe",
        "shadow": "#d6dee2", "gradient_start": "#f7fafb",
        "gradient_middle": "#dce8ee", "gradient_end": "#b9ccd7",
        "gradient_text": "#28343b", "gradient_subtext": "#5f707a",
    },
    "Sand & Teal": {
        "bg": "#f2efe8", "card": "#fbfaf6", "border": "#d5cfc3",
        "text": "#303431", "muted": "#6c706c", "accent": "#467a76",
        "accent_hover": "#578b87", "accent_pressed": "#396864",
        "soft": "#e8e3d9", "soft_hover": "#ded8cc", "select_bg": "#d6e6e2",
        "table_alt": "#eef4f1", "rename_bg": "#f6ead2", "entry_bg": "#fffdfa",
        "shadow": "#dfd8cc", "gradient_start": "#faf6ed",
        "gradient_middle": "#dde8e1", "gradient_end": "#b5d0c9",
        "gradient_text": "#2f3835", "gradient_subtext": "#61706c",
    },
    "Rosewood & Cream": {
        "bg": "#f4eeee", "card": "#fcf8f6", "border": "#dac7c5",
        "text": "#392f30", "muted": "#756567", "accent": "#83585e",
        "accent_hover": "#956970", "accent_pressed": "#70484e",
        "soft": "#eee1df", "soft_hover": "#e4d4d2", "select_bg": "#ead6d8",
        "table_alt": "#f4eeee", "rename_bg": "#f8ecd9", "entry_bg": "#fffdfb",
        "shadow": "#e6d7d5", "gradient_start": "#fbf5ef",
        "gradient_middle": "#ecd9d7", "gradient_end": "#d2b2b4",
        "gradient_text": "#3a2f31", "gradient_subtext": "#725f62",
    },
    "Graphite & Amber": {
        "bg": "#efefec", "card": "#f8f8f5", "border": "#c9c8c1",
        "text": "#2f302f", "muted": "#666762", "accent": "#8b6b35",
        "accent_hover": "#9d7b43", "accent_pressed": "#73582c",
        "soft": "#e3e2dc", "soft_hover": "#d8d7d0", "select_bg": "#e6dcc4",
        "table_alt": "#f0f1ef", "rename_bg": "#f4e4bd", "entry_bg": "#fdfdfb",
        "shadow": "#d9d8d1", "gradient_start": "#f8f8f3",
        "gradient_middle": "#e8e0cc", "gradient_end": "#cdbb8f",
        "gradient_text": "#30302d", "gradient_subtext": "#66645c",
    },
}

DEFAULT_COLOR_SCHEME = "Warm Clay"

# Neutral default for new installations; saved themes remain unchanged.
COLOR_SCHEMES['Lab Slate'] = {
    'bg': '#eef2f6', 'card': '#ffffff', 'border': '#d8e0e9',
    'text': '#203047', 'muted': '#586a80', 'accent': '#2663a6',
    'accent_hover': '#3275bc', 'accent_pressed': '#1b4e87',
    'soft': '#f1f5f9', 'soft_hover': '#e4ebf3', 'select_bg': '#daeafa',
    'table_alt': '#f6f8fb', 'rename_bg': '#eaf3fc', 'entry_bg': '#ffffff',
    'shadow': '#e5eaf0', 'gradient_start': '#ffffff', 'gradient_middle': '#f3f7fb',
    'gradient_end': '#e5edf6', 'gradient_text': '#203047', 'gradient_subtext': '#586a80',
}
DEFAULT_COLOR_SCHEME = 'Lab Slate'
