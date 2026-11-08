"""Dashboard canvas grid, alert styles and other fixed dashboard values."""

from ..inline_timers import EndAtCard

# The dashboard canvas uses the mockup's 500 px grid and is scaled with the window.
WIDTH = 500
UNIT = (270, 0)  # picture width, top
FLOW = (76, 230, 30)  # airflow outlet y, spread, length
CHIP = (78, 104)  # status chip top and bottom, at the left
BANNER = (0, 74, WIDTH, 108)
READINGS_TOP, READINGS_HEIGHT = 115, 58
# The target-temperature dial: a 270° ring that opens at the bottom.
DIAL_TOP = 182
DIAL = (250, DIAL_TOP + 150, 120)  # centre x, centre y, radius
DIAL_START, DIAL_SWEEP = 135, 270
MODES_TOP, MODES_HEIGHT = 473, 60
TILE_TOP, TILE_HEIGHT = 542, 70
TIMER_TOP = 621
CANVAS_HEIGHT = TIMER_TOP + EndAtCard.HEIGHT + 1
AIR_COLORS = {"Good": "OK", "Medium": "WARN_TEXT", "Poor": "DANGER"}
ALERTS = {
    "error": ("alert", "DANGER_BG", "DANGER_TEXT", "AC error {code}", "Check the unit, or see troubleshooting in hOn."),
    "defrost": ("snow", "SOFT", "ON_SOFT", "Defrosting", "Heating pauses while the outdoor unit melts ice."),
    "filter": (
        "wrench",
        "WARN_BG",
        "WARN_TEXT",
        "Clean the air filter",
        "The AC reports that its filter needs cleaning.",
    ),
}
# What the dial says above the number, by mode.
VERBS = {"Cool": "Cooling to", "Heat": "Heating to", "Dry": "Drying at", "Fan": "Fan only", "Auto": "Holding at"}
FAN_LEVELS = {"Low": 1, "Medium": 2, "High": 3}
# The window opens at its minimum size and stays fixed; the layout is designed for it.
WINDOW_SIZE = (540, 920)
THEME_CHOICES = [
    {"label": "Follow Windows", "value": "system", "glyph": "monitor", "description": "Match the Windows app mode"},
    {"label": "Light mode", "value": "light", "glyph": "sun", "description": "Sand and white surfaces"},
    {"label": "Dark mode", "value": "dark", "glyph": "moon", "description": "Charcoal surfaces for low light"},
]


def equal(left, right):
    try:
        return float(left) == float(right)
    except (ValueError, TypeError):
        return str(left) == str(right)
