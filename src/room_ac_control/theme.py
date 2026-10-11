"""Canvas artwork for the compact AC dashboard, drawn as native vectors."""
import math
import tkinter as tk
from pathlib import Path

BG = "#0d0f0e"
CARD = "#1b1e1b"
HOVER = "#30382e"
TEXT = "#edeee6"
MUTED = "#90978b"
ACCENT = "#b6b29a"
GREEN = "#a6c29a"


def unit_photo(master, width=390):
    """Load original, unbranded appliance artwork."""
    photo = tk.PhotoImage(master=master, file=str(Path(__file__).resolve().parent / "assets" / "unit.png"))
    factor = max(1, math.ceil(photo.width() / width))
    return photo.subsample(factor)


def rounded(canvas, x1, y1, x2, y2, radius=12, **options):
    points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)


def icon(canvas, name, x, y, color=ACCENT):
    line = lambda *p: canvas.create_line(*p, fill=color, width=1.6, capstyle="round")
    if name == "unit":
        rounded(canvas,x-13,y-8,x+13,y+8,3,fill="",outline=color,width=1.4)
        line(x-9,y+4,x+9,y+4)
    elif name == "snow":
        for angle in (0, 60, 120):
            dx, dy = 12*math.cos(math.radians(angle)), 12*math.sin(math.radians(angle))
            line(x-dx,y-dy,x+dx,y+dy)
            for sign in (-1,1):
                ex,ey=x+sign*dx,y+sign*dy
                for offset in (-35,35):
                    a=math.radians(angle+offset)
                    line(ex,ey,ex-sign*5*math.cos(a),ey-sign*5*math.sin(a))
    elif name == "fan":
        for angle in (0,90,180,270):
            a=math.radians(angle)
            dx,dy=8*math.cos(a),8*math.sin(a)
            canvas.create_oval(x+dx-5,y+dy-5,x+dx+5,y+dy+5,outline=color,width=1.4)
        canvas.create_oval(x-3,y-3,x+3,y+3,fill=CARD,outline=color)
    elif name == "moon":
        canvas.create_oval(x-11,y-12,x+11,y+10,outline=color,width=1.5)
        canvas.create_oval(x-3,y-16,x+16,y+3,fill=CARD,outline=CARD)
    elif name == "wind":
        for offset, length in ((-6,16),(0,22),(6,14)):
            line(x-12,y+offset,x+length-12,y+offset)
            canvas.create_arc(x+length-17,y+offset-7,x+length-6,y+offset+1,start=0,extent=170,style="arc",outline=color,width=1.5)
    elif name == "leaf":
        canvas.create_polygon(x-10,y-8,x+10,y-5,x+8,y+8,x-4,y+5,fill=color,smooth=True)
        line(x-10,y-6,x+12,y+10)
    elif name == "sun":
        canvas.create_oval(x-6,y-6,x+6,y+6,outline=color,width=1.5)
        for angle in range(0,360,45):
            a=math.radians(angle)
            line(x+9*math.cos(a),y+9*math.sin(a),x+13*math.cos(a),y+13*math.sin(a))
    elif name == "drop":
        canvas.create_polygon(x,y-13,x-9,y+1,x-8,y+10,x,y+13,x+8,y+10,x+9,y+1,
                              fill="",outline=color,width=1.5,smooth=True)


def ac_art(canvas, x, y, running=False, target="23", photo=None):
    """Original appliance illustration; airflow is rendered separately."""
    if photo is not None:
        canvas.create_image(x,y,image=photo)
        return
    canvas.create_polygon(x+108,y-22,x+121,y-15,x+121,y+31,x+107,y+37,fill="#c7cbc5",outline="#929a90")
    rounded(canvas,x-108,y-30,x+111,y+37,7,fill="#f1f3ee",outline="#c6cdc2",width=1)
    canvas.create_polygon(x-100,y+14,x+105,y+22,x+102,y+35,x-100,y+27,fill="#171b17")
    for n in range(28):
        lx=x-94+n*7
        canvas.create_line(lx,y+18,lx,y+30,fill="#7e877b",width=.7)
    canvas.create_line(x-103,y-18,x+103,y-10,fill="#ffffff",width=2)
    canvas.create_text(x+79,y-15,text=target,fill="#a1a89b",font=("Segoe UI",8))
