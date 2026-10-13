"""Animation lifecycle checks without an account, network, or GUI session."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from room_ac_control.login_loading import LoginLoadingAnimation


class Canvas:
    def __init__(self):
        self.items, self.jobs = {}, {}
        self.serial = 0
        self.mapped, self.window_state, self.width = True, "normal", 500
        self.destroyed = False
    def bind(self, *args, **kwargs): pass
    def winfo_width(self): return self.width
    def winfo_ismapped(self): return self.mapped
    def winfo_toplevel(self): return SimpleNamespace(state=lambda: self.window_state)
    def create(self, *args, **kwargs):
        self.serial += 1
        self.items[self.serial] = kwargs
        return self.serial
    create_arc = create_oval = create_rectangle = create_line = create_text = create
    def itemconfigure(self, item, **kwargs): self.items[item].update(kwargs)
    def move(self, *args): pass
    def delete(self, tag):
        if self.destroyed: raise RuntimeError("Canvas commands are unavailable during destruction")
        self.items = {i: v for i, v in self.items.items() if v.get("tags") != tag}
    def after(self, delay, callback):
        self.serial += 1
        self.jobs[self.serial] = (delay, callback)
        return self.serial
    def after_cancel(self, job): self.jobs.pop(job, None)
    def advance(self, animation):
        _, callback = self.jobs.pop(animation.job)
        callback()


class LoginAnimationTests(unittest.TestCase):
    def setUp(self):
        self.canvas = Canvas()
        self.animation = LoginLoadingAnimation(self.canvas)

    def test_repeated_start_and_frames_keep_one_timer_and_reuse_items(self):
        self.animation.start()
        items = set(self.canvas.items)
        first_angles = [self.canvas.items[i]["start"] for i in self.animation.segments]
        self.animation.start()
        self.assertEqual(len(self.canvas.jobs), 1)
        with patch("room_ac_control.login_loading.time.monotonic", return_value=self.animation.started+.5):
            self.canvas.advance(self.animation)
        self.assertEqual(set(self.canvas.items), items)
        self.assertNotEqual(first_angles, [self.canvas.items[i]["start"] for i in self.animation.segments])
        self.assertEqual(len(self.canvas.jobs), 1)

    def test_hidden_windows_pause_painting_and_maximized_windows_resume(self):
        self.animation.start()
        before = [dict(self.canvas.items[i]) for i in self.animation.segments]
        self.canvas.mapped = False
        self.canvas.advance(self.animation)
        self.assertEqual(before, [self.canvas.items[i] for i in self.animation.segments])
        self.assertEqual(self.canvas.jobs[self.animation.job][0], 250)
        self.canvas.mapped, self.canvas.window_state = True, "zoomed"
        self.canvas.advance(self.animation)
        self.assertEqual(self.canvas.jobs[self.animation.job][0], 40)

    def test_completion_or_failure_cancels_timer_and_retry_can_start_again(self):
        self.animation.start()
        self.animation.stop()
        self.assertFalse(self.animation.active)
        self.assertFalse(self.canvas.jobs)
        self.assertFalse(self.canvas.items)
        self.animation.tick()
        self.assertFalse(self.canvas.jobs)
        self.animation.start(automatic=True)
        self.assertEqual(len(self.canvas.jobs), 1)
        self.animation.close()
        self.animation.start()
        self.assertFalse(self.canvas.jobs)

    def test_external_canvas_destruction_cancels_without_painting_destroyed_widget(self):
        self.animation.start()
        self.canvas.destroyed = True
        self.animation.destroyed(SimpleNamespace(widget=self.canvas))
        self.assertTrue(self.animation.closed)
        self.assertFalse(self.canvas.jobs)
