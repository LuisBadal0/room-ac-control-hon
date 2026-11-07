"""Anti-aliased canvas shapes.

Tk draws canvas lines, ovals, arcs and polygons with hard, stair-stepped edges on
Windows. These helpers take the same arguments as the Canvas methods, draw the
shape four times larger with Pillow, scale it down smoothly and place the result
as one image item, so edges look as they do in a browser."""
import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

SUPERSAMPLE = 4


def _images(canvas):
    """Rendered images, kept per Tk interpreter: a closed one deletes its images."""
    return canvas._root().__dict__.setdefault("smooth_images", {})


# Rendered images kept for reuse. Past this, images no widget shows are dropped.
CACHE_LIMIT = 4000


def _keep(canvas, key, photo):
    """Cache a rendered image for reuse.

    When the cache is full, only images that no canvas or widget shows are dropped:
    dropping one still on screen deletes it in Tk and blanks that text or shape in
    every open window."""
    cache = _images(canvas)
    root = canvas._root().__dict__
    if len(cache) >= root.get("smooth_limit", CACHE_LIMIT):
        inuse = canvas.tk.call
        for old in [old for old, image in cache.items() if not inuse("image", "inuse", str(image))]:
            del cache[old]
        # If most images are on screen, wait for another quarter before checking again.
        root["smooth_limit"] = max(CACHE_LIMIT, len(cache) + CACHE_LIMIT//4)
    cache[key] = photo
    return photo


def _key(ops, extent):
    """The cache key for recorded shapes. Tags name canvas items (icons get a new one
    each time) and do not change how a shape looks, so they are left out."""
    return (repr([[kind, coords, {name: value for name, value in options.items() if name != "tags"}]
                  for kind, coords, options in ops]),) + tuple(extent)


def _flatten(values):
    flat = []
    for value in values:
        if isinstance(value, (tuple, list)):
            flat.extend(_flatten(value))
        else:
            flat.append(float(value))
    return flat


def _colour(value):
    return value if value not in ("", None) else None


class Recorder:
    """Collects shapes drawn with Canvas-style calls, to render them together."""

    def __init__(self):
        self.ops = []

    def create_line(self, *coords, **options):
        self.ops.append(["line", _flatten(coords), options])

    def create_oval(self, *coords, **options):
        self.ops.append(["oval", _flatten(coords), options])

    def create_rectangle(self, *coords, **options):
        self.ops.append(["rect", _flatten(coords), options])

    def create_polygon(self, *coords, **options):
        self.ops.append(["polygon", _flatten(coords), options])

    def create_arc(self, *coords, **options):
        self.ops.append(["arc", _flatten(coords), options])

    def create_rounded(self, x1, y1, x2, y2, radius, **options):
        self.ops.append(["rounded", [x1, y1, x2, y2], dict(options, radius=radius)])

    def transform(self, x, y, scale=1, rotate=0):
        """Scale about (x, y), and turn clockwise by rotate degrees, as the icons need."""
        angle = math.radians(rotate)
        cos, sin = math.cos(angle), math.sin(angle)

        def point(px, py):
            dx, dy = (px-x)*scale, (py-y)*scale
            return x+dx*cos-dy*sin, y+dx*sin+dy*cos
        for op in self.ops:
            kind, coords, options = op
            if kind in {"line", "polygon"}:
                moved = []
                for px, py in zip(coords[::2], coords[1::2]):
                    moved.extend(point(px, py))
                op[1] = moved
            else:
                cx, cy = (coords[0]+coords[2])/2, (coords[1]+coords[3])/2
                half_w, half_h = (coords[2]-coords[0])/2*scale, (coords[3]-coords[1])/2*scale
                nx, ny = point(cx, cy)
                op[1] = [nx-half_w, ny-half_h, nx+half_w, ny+half_h]
                if kind == "arc" and rotate:
                    options["start"] = float(options.get("start", 0))-rotate
                if kind == "rounded":
                    options["radius"] = options["radius"]*scale
            if "width" in options:
                options["width"] = float(options["width"])*scale


def _spline(points, closed):
    """Tk's smooth=True curve: quadratic Béziers through the midpoints of each edge."""
    pairs = list(zip(points[::2], points[1::2]))
    if len(pairs) < 3:
        return points
    result = []

    def bezier(a, control, b):
        for step in range(13):
            t = step/12
            result.append(((1-t)**2*a[0]+2*(1-t)*t*control[0]+t*t*b[0], (1-t)**2*a[1]+2*(1-t)*t*control[1]+t*t*b[1]))
    middle = lambda a, b: ((a[0]+b[0])/2, (a[1]+b[1])/2)
    if closed:
        count = len(pairs)
        for i in range(count):
            bezier(middle(pairs[i-1], pairs[i]), pairs[i], middle(pairs[i], pairs[(i+1) % count]))
    else:
        result.append(pairs[0])
        for i in range(1, len(pairs)-1):
            start = pairs[0] if i == 1 else middle(pairs[i-1], pairs[i])
            end = pairs[-1] if i == len(pairs)-2 else middle(pairs[i], pairs[i+1])
            bezier(start, pairs[i], end)
    return [value for pair in result for value in pair]


def _extent(ops):
    xs, ys = [], []
    for kind, coords, options in ops:
        pad = float(options.get("width", 1 if kind in {"line", "arc"} else 0) or 0)/2+1
        if _colour(options.get("outline")) is None and kind not in {"line", "arc"}:
            pad = 1
        xs += [value-pad for value in coords[::2]] + [value+pad for value in coords[::2]]
        ys += [value-pad for value in coords[1::2]] + [value+pad for value in coords[1::2]]
    return math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))


def _render(ops, left, top, right, bottom):
    s = SUPERSAMPLE
    width, height = max(1, right-left), max(1, bottom-top)
    image = Image.new("RGBA", (width*s, height*s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    at = lambda values: [(value-(left if index % 2 == 0 else top))*s for index, value in enumerate(values)]
    for kind, coords, options in ops:
        fill = _colour(options.get("fill"))
        outline = _colour(options.get("outline"))
        stroke = float(options.get("width", 1) or 0)*s
        if kind == "line":
            colour = fill or "#000000"
            points = at(_spline(coords, False) if options.get("smooth") else coords)
            pairs = list(zip(points[::2], points[1::2]))
            if len(pairs) >= 2:
                draw.line(pairs, fill=colour, width=max(1, round(stroke)), joint="curve")
                if options.get("capstyle", "round") != "butt":
                    radius = stroke/2
                    for px, py in (pairs[0], pairs[-1]):
                        draw.ellipse((px-radius, py-radius, px+radius, py+radius), fill=colour)
            continue
        box = None
        if kind != "polygon":
            x0, y0, x1, y1 = at(coords[:4])
            box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            if box[2]-box[0] < 1 or box[3]-box[1] < 1:
                continue
        if kind == "oval":
            if fill:
                draw.ellipse(box, fill=fill)
            if outline and stroke:
                half = stroke/2
                draw.ellipse((box[0]-half, box[1]-half, box[2]+half, box[3]+half), outline=outline,
                             width=max(1, round(stroke)))
        elif kind == "rect":
            if fill:
                draw.rectangle(box, fill=fill)
            if outline and stroke:
                half = stroke/2
                draw.rectangle((box[0]-half, box[1]-half, box[2]+half, box[3]+half), outline=outline,
                               width=max(1, round(stroke)))
        elif kind == "rounded":
            radius = max(0, min(float(options.get("radius", 0))*s, (box[2]-box[0])/2, (box[3]-box[1])/2))
            if fill:
                draw.rounded_rectangle(box, radius=radius, fill=fill)
            if outline and stroke:
                half = stroke/2
                draw.rounded_rectangle((box[0]-half, box[1]-half, box[2]+half, box[3]+half), radius=radius+half,
                                       outline=outline, width=max(1, round(stroke)))
        elif kind == "polygon":
            points = at(_spline(coords, True) if options.get("smooth") else coords)
            pairs = list(zip(points[::2], points[1::2]))
            if len(pairs) < 2:
                continue
            if fill:
                draw.polygon(pairs, fill=fill)
            if outline and stroke:
                draw.line(pairs+[pairs[0]], fill=outline, width=max(1, round(stroke)), joint="curve")
        elif kind == "arc":
            start = float(options.get("start", 0))
            extent = float(options.get("extent", 90))
            # Tk measures counter-clockwise; Pillow clockwise.
            first, last = (-(start+extent), -start) if extent >= 0 else (-start, -(start+extent))
            style = options.get("style", "pieslice")
            if style == "arc":
                colour = outline or "#000000"
                half = stroke/2
                draw.arc((box[0]-half, box[1]-half, box[2]+half, box[3]+half), first, last, fill=colour,
                         width=max(1, round(stroke)))
            elif style == "chord":
                draw.chord(box, first, last, fill=fill, outline=outline)
            else:
                draw.pieslice(box, first, last, fill=fill, outline=outline)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def sprite(canvas, ops, tags=(), state=None):
    """Place the recorded shapes on the canvas as one anti-aliased image item."""
    if not ops:
        return canvas.create_rectangle(0, 0, 0, 0, outline="", tags=tags)
    left, top, right, bottom = _extent(ops)
    key = _key(ops, (left, top, right, bottom))
    photo = _images(canvas).get(key)
    if photo is None:
        photo = _keep(canvas, key, ImageTk.PhotoImage(_render(ops, left, top, right, bottom), master=canvas))
    options = {"state": state} if state else {}
    item = canvas.create_image(left, top, image=photo, anchor="nw", tags=tags, **options)
    registry = canvas.__dict__.setdefault("smooth_items", {})
    if len(registry) > 3000:
        alive = set(canvas.find_all())
        for stale in [key for key in registry if key not in alive]:
            del registry[stale]
    registry[item] = ops
    return item


def _shape(kind, canvas, coords, options):
    if not isinstance(canvas, (tk.Canvas, Recorder)):
        return getattr(canvas, {"rect": "create_rectangle"}.get(kind, f"create_{kind}"))(*coords, **options)
    if isinstance(canvas, Recorder):
        return getattr(canvas, {"rect": "create_rectangle"}.get(kind, f"create_{kind}"))(*coords, **options)
    tags = options.pop("tags", ())
    state = options.pop("state", None)
    if isinstance(tags, str):
        tags = (tags,)
    return sprite(canvas, [[kind, _flatten(coords), options]], tags, state)


def aa_line(canvas, *coords, **options):
    return _shape("line", canvas, coords, options)


def aa_oval(canvas, *coords, **options):
    return _shape("oval", canvas, coords, options)


def aa_rect(canvas, *coords, **options):
    return _shape("rect", canvas, coords, options)


def aa_polygon(canvas, *coords, **options):
    return _shape("polygon", canvas, coords, options)


def aa_arc(canvas, *coords, **options):
    return _shape("arc", canvas, coords, options)


def aa_rounded(canvas, x1, y1, x2, y2, radius, **options):
    if not isinstance(canvas, (tk.Canvas, Recorder)):
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2, x2-radius, y2,
                  x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)
    if isinstance(canvas, Recorder):
        return canvas.create_rounded(x1, y1, x2, y2, radius, **options)
    tags = options.pop("tags", ())
    state = options.pop("state", None)
    if isinstance(tags, str):
        tags = (tags,)
    for unused in ("smooth", "splinesteps", "joinstyle"):
        options.pop(unused, None)
    return sprite(canvas, [["rounded", [x1, y1, x2, y2], dict(options, radius=radius)]], tags, state)


def restyle(canvas, item, **changes):
    """itemconfigure for smooth items: re-render with a new fill, outline, width or text."""
    if not isinstance(canvas, tk.Canvas):
        return canvas.itemconfigure(item, **changes)
    label = canvas.__dict__.get("smooth_texts", {}).get(item)
    if label is not None:
        settings = dict(label, **changes)
        face = pil_font(canvas, settings["font"])
        key = ("text", settings["text"], settings["font"], settings["fill"], settings["width"], settings["justify"])
        photo = _images(canvas).get(key)
        if photo is None:
            image = _text_image(face, settings["text"], settings["fill"],
                                float(settings["width"]) if settings["width"] else None, settings["justify"])
            photo = _keep(canvas, key, ImageTk.PhotoImage(image, master=canvas))
        across, down = ANCHORS.get(settings["anchor"], (.5, .5))
        canvas.itemconfigure(item, image=photo)
        canvas.coords(item, round(settings["x"]-across*(photo.width()-2)-1), round(settings["y"]-down*(photo.height()-2)-1))
        canvas.__dict__["smooth_texts"][item] = settings
        return item
    ops = canvas.__dict__.get("smooth_items", {}).get(item)
    if ops is None:
        canvas.itemconfigure(item, **changes)
        return
    updated = [[kind, coords, dict(options, **changes)] for kind, coords, options in ops]
    if updated == ops:
        return
    left, top, right, bottom = _extent(updated)
    key = _key(updated, (left, top, right, bottom))
    photo = _images(canvas).get(key)
    if photo is None:
        photo = _keep(canvas, key, ImageTk.PhotoImage(_render(updated, left, top, right, bottom), master=canvas))
    canvas.itemconfigure(item, image=photo)
    canvas.coords(item, left, top)
    canvas.__dict__["smooth_items"][item] = updated


# Text, drawn with the bundled fonts through FreeType so letters are smoothed
# (greyscale anti-aliasing) as in a browser, instead of Windows ClearType.

FONT_FILES = {
    "Manrope Light": ("Manrope-Light.ttf", None), "Manrope": ("Manrope-Regular.ttf", "Manrope-Bold.ttf"),
    "Manrope SemiBold": ("Manrope-SemiBold.ttf", None), "Manrope ExtraBold": ("Manrope-ExtraBold.ttf", None),
    "Segoe UI Light": ("C:/Windows/Fonts/segoeuil.ttf", None), "Segoe UI": ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    "Segoe UI Semibold": ("C:/Windows/Fonts/seguisb.ttf", None), "Segoe UI Black": ("C:/Windows/Fonts/seguibl.ttf", None),
}
_fonts = {}


def pil_font(widget, spec):
    """The Pillow font for a Tk font tuple such as ("Manrope", 12, "bold"), or None."""
    from pathlib import Path
    from PIL import ImageFont
    if not isinstance(spec, tuple) or len(spec) < 2:
        return None
    family, size = spec[0], int(spec[1])
    bold = "bold" in spec[2:]
    if family not in FONT_FILES:
        return None
    pixels = -size if size < 0 else round(size*widget.winfo_fpixels("1p"))
    key = (family, pixels, bold)
    if key not in _fonts:
        regular, heavy = FONT_FILES[family]
        name = heavy if bold and heavy else regular
        path = Path(name) if ":" in name else Path(__file__).resolve().parent / "assets" / "fonts" / name
        try:
            _fonts[key] = ImageFont.truetype(str(path), pixels)
        except OSError:
            _fonts[key] = None
    return _fonts[key]


def _wrap(font, text, width):
    lines = []
    for paragraph in str(text).split("\n"):
        if not width:
            lines.append(paragraph)
            continue
        current = ""
        for word in paragraph.split(" "):
            trial = word if not current else current + " " + word
            if font.getlength(trial) <= width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


ANCHORS = {"nw": (0, 0), "n": (.5, 0), "ne": (1, 0), "w": (0, .5), "center": (.5, .5), "e": (1, .5),
           "sw": (0, 1), "s": (.5, 1), "se": (1, 1)}


def _text_image(font, text, fill, width, justify):
    from PIL import Image, ImageDraw
    lines = _wrap(font, text, width)
    ascent, descent = font.getmetrics()
    line_height = ascent+descent
    widths = [font.getlength(line) for line in lines]
    block = math.ceil(max(widths or [0]))
    image = Image.new("RGBA", (block+2, line_height*len(lines)+2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, (line, line_width) in enumerate(zip(lines, widths)):
        offset = (block-line_width)/2 if justify == "center" else (block-line_width if justify == "right" else 0)
        draw.text((1+offset, 1+index*line_height), line, font=font, fill=fill)
    return image


def aa_text(canvas, x, y, text="", font=None, fill="#000000", anchor="center", width=None, tags=(), justify="left",
            state=None, **options):
    """Canvas.create_text, but smooth; falls back to Tk text for fonts that are not bundled."""
    face = pil_font(canvas, font) if isinstance(canvas, tk.Canvas) else None
    if face is None:
        extra = {"width": width} if width else {}
        return canvas.create_text(x, y, text=text, font=font, fill=fill, anchor=anchor, tags=tags, justify=justify,
                                  **({"state": state} if state else {}), **extra, **options)
    if isinstance(tags, str):
        tags = (tags,)
    key = ("text", text, font, fill, width, justify)
    photo = _images(canvas).get(key)
    if photo is None:
        image = _text_image(face, text, fill, float(width) if width else None, justify)
        photo = _keep(canvas, key, ImageTk.PhotoImage(image, master=canvas))
    across, down = ANCHORS.get(anchor, (.5, .5))
    left = x-across*(photo.width()-2)-1
    top = y-down*(photo.height()-2)-1
    item = canvas.create_image(round(left), round(top), image=photo, anchor="nw", tags=tags,
                               **({"state": state} if state else {}))
    labels = canvas.__dict__.setdefault("smooth_texts", {})
    if len(labels) > 3000:  # Forget texts whose canvas items were deleted, as sprite() does.
        alive = set(canvas.find_all())
        for stale in [key for key in labels if key not in alive]:
            del labels[stale]
    labels[item] = {"x": x, "y": y, "text": text, "font": font, "fill": fill,
                    "anchor": anchor, "width": width, "justify": justify}
    return item


def texts(canvas):
    """Visible text on a canvas, smooth or native, as (item, text) pairs in drawing order."""
    smooth = canvas.__dict__.get("smooth_texts", {})
    result = []
    for item in canvas.find_all():
        if item in smooth:
            result.append((item, str(smooth[item]["text"])))
        elif canvas.type(item) == "text":
            result.append((item, canvas.itemcget(item, "text")))
    return result


def text_width(widget, text, spec):
    face = pil_font(widget, spec)
    return None if face is None else face.getlength(str(text))
