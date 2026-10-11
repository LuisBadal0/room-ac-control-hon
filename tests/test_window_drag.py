"""Fast pointer events must not trigger a geometry change for every sample."""
from types import SimpleNamespace
import unittest

from room_ac_control.window_header import WindowHeader


class Window:
    def __init__(self):
        self.jobs = {}
        self.next_job = 0
    def state(self): return "normal"
    def after(self, delay, callback):
        self.next_job += 1
        self.jobs[self.next_job] = callback
        return self.next_job
    def after_cancel(self, job): self.jobs.pop(job)


class Native:
    hwnd = 1
    def __init__(self):
        self.moves = []
        self.repaints = 0
    def position(self): return (100, 200)
    def move_to(self, x, y): self.moves.append((x, y))
    def repaint(self): self.repaints += 1


class DragTests(unittest.TestCase):
    def header(self):
        header = WindowHeader.__new__(WindowHeader)
        header.window = Window()
        header.native = Native()
        header.drag_origin = header.drag_pending = header.drag_job = None
        return header

    def test_fast_events_coalesce_and_release_keeps_final_position(self):
        header = self.header()
        header.drag(SimpleNamespace(x_root=120, y_root=225))
        for sample in range(300):
            header.drag_motion(SimpleNamespace(x_root=120+sample, y_root=225+sample))
        self.assertEqual(len(header.window.jobs), 1)
        self.assertEqual(header.native.moves, [])
        header.end_drag()
        self.assertEqual(header.native.moves, [(399, 499)])
        self.assertEqual(header.native.repaints, 1)
        self.assertEqual(header.window.jobs, {})
        self.assertIsNone(header.drag_pending)

    def test_next_frame_and_negative_monitor_coordinates(self):
        header = self.header()
        header.drag(SimpleNamespace(x_root=120, y_root=225))
        header.drag_motion(SimpleNamespace(x_root=-200, y_root=-100))
        header.window.jobs.pop(header.drag_job)()
        self.assertEqual(header.native.moves, [(-220, -125)])
        header.drag_motion(SimpleNamespace(x_root=200, y_root=300))
        self.assertEqual(len(header.window.jobs), 1)
        header.end_drag()
        self.assertEqual(header.native.moves[-1], (180, 275))

    def test_destroy_cancels_pending_movement(self):
        header = self.header()
        header.drag(SimpleNamespace(x_root=120, y_root=225))
        header.drag_motion(SimpleNamespace(x_root=220, y_root=325))
        header.destroyed(SimpleNamespace(widget=header.window))
        self.assertEqual(header.window.jobs, {})
        self.assertEqual(header.native.moves, [])
        self.assertIsNone(header.drag_origin)
