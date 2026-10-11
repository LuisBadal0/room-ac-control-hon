"""Highlight canvas controls without rebuilding their artwork or animation."""
class CanvasHover:
    def __init__(self, canvas):
        self.canvas = canvas
        self.pointer = None
        self.regions = []
        self.active = set()
        self.scale = 1
        self.enabled = True
        canvas.bind("<Motion>",self.motion,add="+")
        canvas.bind("<Leave>",self.leave,add="+")

    def reset(self, scale=1, enabled=True):
        self.regions = []
        self.active = set()
        self.scale = scale
        self.enabled = enabled

    def add(self, box, item, normal, hover):
        self.regions.append((box,item,normal,hover))

    def motion(self, event):
        self.pointer = (event.x,event.y)
        self.update()

    def leave(self, event=None):
        self.pointer = None
        self.update()

    def update(self):
        active = set()
        if self.pointer is not None and self.enabled:
            x,y = (coordinate/self.scale for coordinate in self.pointer)
            active = {index for index,(box,*_) in enumerate(self.regions)
                      if box[0]<=x<=box[2] and box[1]<=y<=box[3]}
        for index in self.active | active:
            if index in self.active and index in active:continue
            _,item,normal,hover = self.regions[index]
            self.canvas.itemconfigure(item,**(hover if index in active else normal))
        self.active = active
        self.canvas.configure(cursor="hand2" if active else "")
