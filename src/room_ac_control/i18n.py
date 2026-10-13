"""Display-only translations; cloud keys, values and saved program names stay stable."""
import ctypes
from ctypes import wintypes
import locale
import re
from string import Formatter
import tkinter as tk
import unicodedata

from .translations import PORTUGUESE

LANGUAGES = {"en": "English", "pt-PT": "Português (Portugal)"}
PREFERENCES = {"system", *LANGUAGES}


def system_language():
    """Use the Windows display language, rather than its number-format region."""
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_language = kernel.GetUserDefaultUILanguage
        get_language.argtypes = []
        get_language.restype = wintypes.WORD
        return locale.windows_locale.get(get_language(), "en")
    except (AttributeError, OSError):
        return locale.getlocale()[0] or "en"


def resolve_language(value):
    return "pt-PT" if str(value).lower().replace("_", "-").split("-")[0] == "pt" else "en"


class Translator:
    def __init__(self, preference="system"):
        self.set_language(preference)

    def set_language(self, preference):
        self.preference = preference if isinstance(preference, str) and preference in PREFERENCES else "system"
        self.language = resolve_language(system_language() if self.preference == "system" else self.preference)

    def translate(self, message):
        message = str(message)
        if self.language == "en":
            return message
        if message in PORTUGUESE:
            return PORTUGUESE[message]
        for pattern, fields, target in TEMPLATES:
            if match := pattern.fullmatch(message):
                values = dict(zip(fields, match.groups()))
                return "".join(literal + ((self.number(values[field]) if field in {"min","max","step","count","value"}
                                           else self.translate(values[field])) if field else "")
                               for literal, field, _, _ in Formatter().parse(target))
        # These separators combine independent application labels, not wire values.
        for separator in (" · ", " — "):
            if separator in message:
                return separator.join(self.translate(part) for part in message.split(separator))
        for prefix in ("●  ", "◇ ", "♧  ", "↻ "):
            if message.startswith(prefix):
                return prefix + self.translate(message[len(prefix):])
        return message

    def number(self, value):
        text = str(value)
        return text.replace(".", ",") if self.language == "pt-PT" else text

    def date(self, value):
        if self.language == "en":
            days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            return f"{days[value.weekday()]} {value.day:02d} {months[value.month-1]}"
        days = ("seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom.")
        months = ("jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez.")
        return f"{days[value.weekday()]} {value.day:02d} {months[value.month-1]}"


def _templates():
    result = []
    for source, target in PORTUGUESE.items():
        if "{" not in source:
            continue
        parts, fields = [], []
        for literal, field, _, _ in Formatter().parse(source):
            parts.append(re.escape(literal))
            if field:
                fields.append(field)
                parts.append("(.+?)")
        result.append((re.compile("".join(parts), re.DOTALL), fields, target))
    return result


TEMPLATES = _templates()
ENGLISH = Translator("en")


def translator(widget):
    while widget is not None:
        if language := getattr(widget, "i18n", None):
            return language
        widget = getattr(widget, "master", None)
    return ENGLISH


def tr(widget, message):
    return translator(widget).translate(message)


def refresh_on_language(widget, callback):
    widget.bind("<<LanguageChanged>>", lambda event: callback() if event.widget is widget else None, add="+")


def localized(widget):
    """Keep the source label so switching back to English is lossless."""
    source = widget.cget("text")
    if source:
        refresh = lambda: widget.configure(text=tr(widget, source))
        refresh()
        refresh_on_language(widget, refresh)
    return widget


class TranslatedVariable(tk.StringVar):
    def __init__(self, master, source):
        super().__init__(master)
        self.source, self.master = source, master
        self.source_trace = source.trace_add("write", self.refresh)
        refresh_on_language(master, self.refresh)
        self.refresh()

    def refresh(self, *args):
        self.set(tr(self.master, self.source.get()))


def localized_title(window, source):
    refresh = lambda: window.title(tr(window, source))
    refresh()
    refresh_on_language(window, refresh)


def broadcast_language(root):
    def visit(widget):
        children = list(widget.winfo_children())
        widget.event_generate("<<LanguageChanged>>")
        for child in children:
            if child.winfo_exists():
                visit(child)
    visit(root)


def search_text(parts):
    portuguese = Translator("pt-PT")
    text = " ".join(str(part) for part in parts)
    text += " " + " ".join(portuguese.translate(part) for part in parts)
    return "".join(character for character in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(character))
