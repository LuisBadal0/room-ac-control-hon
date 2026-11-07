"""One Room AC Control per Windows session.

A second start asks the running app to show its window, then exits. Two running
copies would also lock the app folder against each other, so an update could not
replace it."""

import ctypes
import os

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
ASFW_ANY = -1


class SingleInstance:
    def __init__(self, name="RoomACControl"):
        self.mutex = self.event = None
        self.first = True
        if os.name != "nt":
            return
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateEventW.restype = wintypes.HANDLE
        kernel.SetEvent.argtypes = [wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        # "Local\" keeps each signed-in Windows session separate.
        self.mutex = kernel.CreateMutexW(None, False, f"Local\\{name}.Instance")
        self.first = not (self.mutex and ctypes.get_last_error() == ERROR_ALREADY_EXISTS)
        # Auto-reset: each signal shows the window once.
        self.event = kernel.CreateEventW(None, False, False, f"Local\\{name}.Show")

    def show_running(self):
        """From a second start: let the running copy come to the front and show its window."""
        if not self.event:
            return
        try:
            ctypes.WinDLL("user32").AllowSetForegroundWindow(ASFW_ANY)
        except (AttributeError, OSError):
            pass
        self.kernel.SetEvent(self.event)

    def show_requested(self):
        """In the running copy: whether another start asked to show the window."""
        return bool(self.event) and self.kernel.WaitForSingleObject(self.event, 0) == WAIT_OBJECT_0

    def close(self):
        for handle in (self.event, self.mutex):
            if handle:
                self.kernel.CloseHandle(handle)
        self.mutex = self.event = None
