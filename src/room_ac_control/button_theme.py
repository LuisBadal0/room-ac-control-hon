"""Rounded action-button surfaces, retaining native ttk input and focus behavior."""
from PIL import Image, ImageDraw, ImageTk

from .theme import BG, CARD, HOVER, TEXT, ACCENT


def _surface(master, fill, outline=None):
    scale = 3
    image = Image.new("RGBA", (32*scale,32*scale))
    ImageDraw.Draw(image).rounded_rectangle((scale,scale,31*scale,31*scale),
                                           radius=6*scale,fill=fill,outline=outline,width=scale)
    return ImageTk.PhotoImage(image.resize((32,32),Image.Resampling.LANCZOS),master=master)


def install_button_theme(root, style):
    # Nine-slice images keep the corners round at every button width. Native ttk
    # buttons still handle disabled states, keyboard activation and accessibility.
    images = []
    for name in ("TButton","Accent.TButton"):
        palettes = ((CARD,None),(CARD,None),("#252d23",ACCENT),(HOVER,ACCENT),(CARD,ACCENT))
        surfaces = [_surface(root,*palette) for palette in palettes]
        images.extend(surfaces)
        element = "RoomAC."+name+".surface"
        style.element_create(element,"image",surfaces[0],("disabled",surfaces[1]),
                             ("pressed",surfaces[2]),("active",surfaces[3]),("focus",surfaces[4]),
                             border=8,padding=0,sticky="nsew")
        style.layout(name,[(element,{"sticky":"nsew","children":[
            ("Button.padding",{"sticky":"nsew","children":[("Button.label",{"sticky":"nsew"})]})]})])
        style.configure(name,background=BG,foreground=TEXT,padding=(12,10),font=("Segoe UI",10,"bold"),anchor="center")
        style.map(name,foreground=[("disabled","#656d60")],background=[])
    style.configure("Login.Accent.TButton",padding=(14,12),font=("Segoe UI",11,"bold"),background=CARD)
    style.configure("Card.TButton",background=CARD)
    # Keep Python references for as long as ttk uses these image elements.
    root.button_theme_images = images
