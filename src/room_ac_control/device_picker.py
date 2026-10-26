"""A room dropdown card, theme-matched room chooser and the round power button."""
from .i18n import tr, refresh_on_language
import tkinter as tk
from tkinter import font as tkfont

from .choice_widgets import ChoicePanel
from .theme import C, font, icon, rounded, refresh_on_theme


class DevicePicker(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent,height=60,highlightthickness=0,takefocus=False)
        self.command = command
        self.devices = []
        self.index = 0
        self.enabled = False
        self.hover = False
        self.name_font = tkfont.Font(self,font=font(12,"bold"))
        self.bind("<Configure>",lambda event:self.draw())
        self.bind("<Button-1>",lambda event:self.open())
        self.bind("<Return>",lambda event:self.open())
        self.bind("<space>",lambda event:self.open())
        self.bind("<Enter>",lambda event:self.highlight(True))
        self.bind("<Leave>",lambda event:self.highlight(False))
        self.bind("<FocusIn>",lambda event:self.highlight(True))
        self.bind("<FocusOut>",lambda event:self.highlight(False))
        refresh_on_language(self,self.draw)
        refresh_on_theme(self,self.draw)

    def set_devices(self, devices):
        self.devices = devices
        self.index = 0
        self.draw()

    def current(self, index=None):
        if index is not None:
            if not 0 <= index < len(self.devices):
                raise IndexError("Device index is out of range")
            self.index = index
            self.draw()
        return self.index

    def set_enabled(self, enabled):
        self.enabled = enabled
        selectable = enabled and len(self.devices)>1
        self.configure(cursor="hand2" if selectable else "",takefocus=selectable)
        self.draw()

    def highlight(self, active):
        self.hover = active
        self.draw()

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        width = max(240,self.winfo_width())
        selectable = self.enabled and len(self.devices)>1
        rounded(self,1,1,width-1,59,12,fill=C.HOVER if selectable and self.hover else C.CARD,
                outline=C.BRAND if selectable and self.hover else C.EDGE)
        rounded(self,10,10,50,50,8,fill=C.SURFACE,outline="")
        icon(self,"unit",30,30,C.TEXT,scale=.85,bg=C.SURFACE)
        if not self.devices:
            return
        device = self.devices[self.index]
        name = device["name"]
        available = width-150
        if self.name_font.measure(name)>available:
            while name and self.name_font.measure(name+"…")>available:name=name[:-1]
            name += "…"
        self.create_text(62,21,text=name,anchor="w",fill=C.TEXT if self.enabled else C.MUTED,font=self.name_font)
        self.create_text(62,41,text=device["model"],anchor="w",fill=C.MUTED,font=font(9))
        if selectable:
            icon(self,"chevron",width-24,30,C.MUTED)
        else:
            connected = device.get("connection")=="CONNECTED"
            label = self.create_text(width-16,30,text=tr(self, "Connected" if connected else "Offline" if device.get("connection")=="DISCONNECTED" else "Unknown"),
                                     anchor="e",fill=C.OK_TEXT if connected else C.MUTED,font=font(9,"bold"))
            left = self.bbox(label)[0]
            self.create_oval(left-12,26,left-5,33,fill=C.OK if connected else C.FAINT,outline="")

    def open(self):
        if not self.enabled or len(self.devices)<2:
            return
        options = [{"label":device["name"],"description":device["model"],"value":index,"glyph":"unit","translate_label":False}
                   for index,device in enumerate(self.devices)]
        def choose(index):
            self.current(index)
            self.command()
        self.choice_panel = ChoicePanel(self,"Your air conditioners",options,self.index,choose)


class PowerButton(tk.Canvas):
    """Brand-filled when the AC reports On; outlined when Off."""
    def __init__(self, parent, command):
        super().__init__(parent,width=60,height=60,highlightthickness=0,takefocus=True,cursor="hand2")
        self.command = command
        self.on, self.enabled, self.hover = False, False, False
        self.bind("<Button-1>",lambda event:self.invoke())
        self.bind("<Return>",lambda event:self.invoke())
        self.bind("<space>",lambda event:self.invoke())
        self.bind("<Enter>",lambda event:self.highlight(True))
        self.bind("<Leave>",lambda event:self.highlight(False))
        refresh_on_theme(self,self.draw)
        self.draw()

    def set_state(self, on, enabled):
        self.on, self.enabled = on, enabled
        self.configure(cursor="hand2" if enabled else "")
        self.draw()

    def highlight(self, active):
        self.hover = active
        self.draw()

    def invoke(self):
        if self.enabled:
            self.command()

    def draw(self):
        self.delete("all")
        self.configure(bg=C.BG)
        hover = self.hover and self.enabled
        if self.on:
            fill, outline, glyph = (C.BRAND_ACTIVE if hover else C.BRAND), "", C.ON_BRAND
        else:
            fill, outline, glyph = (C.HOVER if hover else C.CARD), (C.BRAND if hover else C.EDGE), C.TEXT
        self.create_oval(1,1,59,59,fill=fill,outline=outline,width=1.5)
        icon(self,"power",30,31,glyph if self.enabled else C.FAINT,bg=fill)
