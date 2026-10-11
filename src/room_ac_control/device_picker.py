"""A device card and theme-matched room chooser."""
import tkinter as tk
from tkinter import font as tkfont

from .choice_widgets import ChoicePanel
from .theme import BG, CARD, HOVER, TEXT, MUTED, ACCENT, GREEN, rounded


class DevicePicker(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent,bg=BG,height=68,highlightthickness=0,takefocus=False)
        self.command = command
        self.devices = []
        self.index = 0
        self.enabled = False
        self.hover = False
        self.name_font = tkfont.Font(self,family="Segoe UI",size=13,weight="bold")
        self.bind("<Configure>",lambda event:self.draw())
        self.bind("<Button-1>",lambda event:self.open())
        self.bind("<Return>",lambda event:self.open())
        self.bind("<space>",lambda event:self.open())
        self.bind("<Enter>",lambda event:self.highlight(True))
        self.bind("<Leave>",lambda event:self.highlight(False))
        self.bind("<FocusIn>",lambda event:self.highlight(True))
        self.bind("<FocusOut>",lambda event:self.highlight(False))

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
        width = max(300,self.winfo_width())
        selectable = self.enabled and len(self.devices)>1
        rounded(self,1,1,width-1,67,15,fill=HOVER if selectable and self.hover else CARD,outline=ACCENT if selectable and self.hover else "#2b3229")
        rounded(self,14,13,57,55,10,fill="#282f27",outline="")
        rounded(self,23,26,49,41,3,fill="",outline=ACCENT,width=1.4)
        self.create_line(26,37,46,37,fill=ACCENT,width=1.4)
        if not self.devices:
            return
        device = self.devices[self.index]
        name = device["name"]
        available = width-202
        if self.name_font.measure(name)>available:
            while name and self.name_font.measure(name+"…")>available:name=name[:-1]
            name += "…"
        self.create_text(72,24,text=name,anchor="w",fill=TEXT if self.enabled else MUTED,font=self.name_font)
        self.create_text(72,47,text=device["model"],anchor="w",fill=MUTED,font=("Segoe UI",9))
        if selectable:
            rounded(self,width-108,18,width-14,50,9,fill="#414a39" if self.hover else "#2d352b",outline="")
            self.create_text(width-61,34,text="Switch",fill=ACCENT,font=("Segoe UI",10))
        else:
            connected = device.get("connection")=="CONNECTED"
            self.create_oval(width-111,29,width-105,35,fill=GREEN if connected else MUTED,outline="")
            self.create_text(width-18,32,text="Connected" if connected else "Offline" if device.get("connection")=="DISCONNECTED" else "Unknown",
                             anchor="e",fill=GREEN if connected else MUTED,font=("Segoe UI",9))

    def open(self):
        if not self.enabled or len(self.devices)<2:
            return
        options = [{"label":device["name"],"description":device["model"],"value":index,"glyph":"unit"}
                   for index,device in enumerate(self.devices)]
        def choose(index):
            self.current(index)
            self.command()
        self.choice_panel = ChoicePanel(self,"Your air conditioners",options,self.index,choose)
