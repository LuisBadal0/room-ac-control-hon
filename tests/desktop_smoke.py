"""Saved-login flow and tray lifecycle without a real account or AC command."""
import queue
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1])); sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.dashboard import App
from room_ac_control.secure_state import SecureState
from tests.ui_smoke import demo_device


with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/"state.dpapi"
    root=tk.Tk();root.withdraw()
    app=App(root,demo=True,state=SecureState(path),enable_tray=False)
    submissions=[]
    def submit(coroutine,callback,operation,on_error=None):
        coroutine.close()
        submissions.append((callback,operation,on_error))
    app.worker.submit=submit
    assert not app.remember_account.get()
    app.sign_in("sample@example.test","fake-desktop-test-password")
    submissions[-1][0]([demo_device()])
    assert app.storage.credentials() is None  # default sign-in never saves a password
    app.remember_account.set(True)
    app.sign_in("sample@example.test","fake-desktop-test-password")
    assert app.storage.credentials() is None  # not stored before successful login
    app.memory.use_account("sample@example.test")
    submissions[-1][0]([demo_device()])
    assert app.storage.credentials() is not None
    app.close()

    root=tk.Tk();root.withdraw()
    reopened=App(root,demo=True,state=SecureState(path),enable_tray=False)
    submissions=[]
    reopened.worker.submit=submit
    reopened.auto_sign_in()
    assert submissions[-1][1]=="login"
    assert reopened.password.get()==""
    assert reopened.busy
    submissions[-1][2]("test connection failed")
    assert not reopened.busy
    assert "Automatic sign-in failed" in reopened.status.get()
    assert reopened.storage.credentials() is not None
    assert reopened.remember_account.get()  # preserve the original opt-in across auto sign-in

    # Minimize only withdraws after the tray confirms it is available.
    class FakeTray:
        def __init__(self):
            self.events=queue.Queue();self.ready=True;self.shown=False;self.stopped=False
        def show(self):self.shown=True;return True
        def hide(self):self.shown=False
        def close(self):self.stopped=True
    class FakeWindow:
        def __init__(self):self.current="iconic";self.hidden=False;self.raised=False
        def state(self):return self.current
        def withdraw(self):self.hidden=True;self.current="withdrawn"
        def deiconify(self):self.current="normal"
        def lift(self):self.raised=True
        def focus_force(self):pass
        def grab_current(self):return None
    real_root=reopened.root
    reopened.root=FakeWindow();reopened.tray=FakeTray()
    reopened.minimize_to_tray()
    assert reopened.root.hidden and reopened.tray.shown
    reopened.restore_window()
    assert reopened.root.current=="normal" and reopened.root.raised and not reopened.tray.shown
    reopened.root=real_root
    tray=reopened.tray
    reopened.close()
    assert tray.stopped
print("Encrypted remember/automatic sign-in and tray minimize/restore/exit checks passed.")
