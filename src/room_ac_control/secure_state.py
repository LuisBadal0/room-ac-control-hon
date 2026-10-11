"""Encrypted account and program state, protected by the current Windows user."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import threading


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise OSError("Encrypted storage requires Windows.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = DataBlob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
                         ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(DataBlob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # UI_FORBIDDEN only; never LOCAL_MACHINE (which would permit other users).
    if not function(ctypes.byref(source), None if decrypt else "Room AC Control account and programs",
                    None, None, None, 1, ctypes.byref(result)):
        raise OSError("Windows could not decrypt saved data." if decrypt else "Windows could not encrypt saved data.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


class SecureState:
    def __init__(self, path=None, persistent=True):
        self.persistent = persistent
        self.path = Path(path) if path else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RoomACControl" / "state.dpapi"
        self.lock = threading.RLock()
        self.data = {"version": 1, "profiles": {}}
        self.load_error = False
        self.dirty = False
        if persistent and self.path.exists():
            try:
                self.data = json.loads(protect(self.path.read_bytes(), decrypt=True).decode("utf-8"))
                if self.data.get("version") != 1 or not isinstance(self.data.get("profiles"), dict):
                    raise ValueError("Unsupported saved state")
                login=self.data.get("login")
                if login is not None and (not isinstance(login,dict) or not all(isinstance(login.get(k),str) for k in ("email","password"))):
                    raise ValueError("Invalid saved account")
                for devices in self.data["profiles"].values():
                    if not isinstance(devices,dict):raise ValueError("Invalid saved profiles")
                    for programs in devices.values():
                        if not isinstance(programs,dict) or not all(isinstance(values,dict) for values in programs.values()):
                            raise ValueError("Invalid saved profiles")
            except (OSError, ValueError, UnicodeError, AttributeError, TypeError):
                self.data = {"version": 1, "profiles": {}}
                self.load_error = True

    def write(self):
        if not self.persistent:
            self.dirty=False
            return
        encrypted = protect(json.dumps(self.data, ensure_ascii=False).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + "." + secrets.token_hex(6) + ".tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.dirty=False
        finally:
            temporary.unlink(missing_ok=True)

    def credentials(self):
        with self.lock:
            login = self.data.get("login", {})
            if login.get("email") and login.get("password"):
                return login["email"], login["password"]
        return None

    def save_credentials(self, email, password):
        with self.lock:
            self.data["login"] = {"email": email, "password": password}
            self.dirty=True
            self.write()

    def forget_credentials(self):
        with self.lock:
            self.data.pop("login", None)
            self.dirty=True
            self.write()

    def profile(self, account, device, program):
        with self.lock:
            return dict(self.data["profiles"].get(account, {}).get(device, {}).get(program, {}))

    def save_profile(self, account, device, program, values):
        if not account or not values:
            return
        with self.lock:
            programs = self.data["profiles"].setdefault(account, {}).setdefault(device, {})
            merged = dict(programs.get(program, {}))
            merged.update(values)
            if programs.get(program) != merged:
                programs[program] = merged
                self.dirty=True
            if self.dirty:
                self.write()
