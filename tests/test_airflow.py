import unittest

from room_ac_control.airflow import AirflowAnimation, airflow_tone, tint


class Canvas:
    def __init__(self):
        self.items = {}
        self.timers = {}
        self.counter = 0
        self.visible = True
        self.window_state = "normal"
    def bind(self, *args, **kwargs): pass
    def delete(self, tag): self.items.clear()
    def create_line(self, *coords, **kwargs):
        self.counter += 1
        self.items[self.counter] = (coords, kwargs)
        return self.counter
    def coords(self, item, *coords):
        self.items[item] = (coords, self.items[item][1])
    def itemconfigure(self, item, **kwargs): self.items[item][1].update(kwargs)
    def tag_lower(self, *args): pass
    def after(self, delay, callback):
        self.counter += 1
        self.timers[self.counter] = (delay, callback)
        return self.counter
    def after_cancel(self, job): self.timers.pop(job)
    def winfo_ismapped(self): return self.visible
    def winfo_toplevel(self): return self
    def state(self): return self.window_state
    def fire(self, animation):
        job = animation.job
        self.timers.pop(job)[1]()


class AirflowTests(unittest.TestCase):
    def test_reported_modes_and_off(self):
        for mode, expected in [("Cool", "cool"), ("Cool Night", "cool"),
                               ("Heat", "heat"), ("Heat Night", "heat"),
                               ("Auto", "neutral"), ("Dry", "neutral"), ("Fan", "neutral")]:
            self.assertEqual(airflow_tone({"mode": mode, "power": "On"}), expected)
            self.assertIsNone(airflow_tone({"mode": mode, "power": "Off"}))
        self.assertIsNone(airflow_tone(None))
        self.assertIsNone(airflow_tone({"mode": "Heat", "power": "Unknown"}))
        self.assertEqual(airflow_tone({"mode": "Cool", "power": "On", "dirty": {"machMode": "4"}}), "cool")

    def test_color_channels(self):
        rgb = lambda value: tuple(int(value[i:i+2], 16) for i in (1, 3, 5))
        cool, heat = rgb(tint("cool", .5)), rgb(tint("heat", .5))
        self.assertGreater(cool[2], cool[0])
        self.assertGreater(heat[0], heat[2])

    def test_motion_reuses_strokes_and_keeps_one_timer(self):
        canvas = Canvas()
        animation = AirflowAnimation(canvas)
        animation.set_state({"mode": "Cool", "power": "On"}, 260, 144, 275, 47)
        animation.paint(0)
        coordinates = [value[0] for value in canvas.items.values()]
        ids = set(canvas.items)
        animation.paint(.5)
        self.assertNotEqual(coordinates, [value[0] for value in canvas.items.values()])
        self.assertEqual(set(canvas.items), ids)
        animation.set_state({"mode": "Heat", "power": "On"}, 260, 144, 275, 47)
        self.assertEqual(animation.tone, "heat")
        self.assertEqual(len(canvas.timers), 1)
        animation.set_state({"mode": "Heat", "power": "Off"}, 260, 144, 275, 47)
        self.assertEqual(canvas.items, {})
        animation.close()
        self.assertEqual(canvas.timers, {})

    def test_hidden_and_minimized_windows_pause_painting(self):
        canvas = Canvas()
        animation = AirflowAnimation(canvas)
        animation.set_state({"mode": "Cool", "power": "On"}, 260, 144, 275, 47)
        frames = []
        animation.paint = frames.append
        canvas.visible = False
        canvas.fire(animation)
        self.assertEqual(frames, [])
        canvas.visible = True
        canvas.window_state = "iconic"
        canvas.fire(animation)
        self.assertEqual(frames, [])
        canvas.window_state = "normal"
        canvas.fire(animation)
        self.assertEqual(len(frames), 1)
        animation.close()
