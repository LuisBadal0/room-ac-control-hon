"""Shared visual choices for the dashboard and All functions."""


def mode_icon(label):
    if "night" in label.lower():
        return "moon"
    return {"auto": "leaf", "cool": "snow", "dry": "drop", "heat": "sun", "fan": "fan"}.get(label.lower(), "wind")


def airflow_icon(label):
    if label == "Swing":
        return "swing"
    if label in {f"Position {n}" for n in range(1, 6)}:
        return f"vane_{label[-1]}"
    return "wind"


def airflow_choices(spec, patch=False):
    """Use human position labels: wire codes differ between the two axes."""
    descriptions = {"Position 1": "Most closed", "Position 2": "Slightly open",
                    "Position 3": "Half open", "Position 4": "Mostly open",
                    "Position 5": "Most open", "Swing": "Automatic swing"}
    return [{"label": label, "value": {spec["key"]: value} if patch else value,
             "glyph": airflow_icon(label),
             "description": " · ".join(filter(None, (spec["label"], descriptions.get(label))))}
            for label, value in spec.get("options", {}).items()]
