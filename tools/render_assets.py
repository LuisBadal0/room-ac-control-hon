"""Render this project's original geometric artwork; no third-party images."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

SS=4  # Supersampling factor for smooth edges.

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'src'/'room_ac_control'/'assets'


def gradient(size,stops):
    """Vertical gradient; stops are (0..1 from the top, '#rrggbb')."""
    width,height=size
    image=Image.new('RGBA',size)
    rgb=[(t,tuple(int(c[i:i+2],16) for i in (1,3,5))) for t,c in stops]
    for y in range(height):
        t=y/max(1,height-1)
        for (t0,a),(t1,b) in zip(rgb,rgb[1:]):
            if t0<=t<=t1:
                k=(t-t0)/max(1e-9,t1-t0)
                color=tuple(round(a[i]+(b[i]-a[i])*k) for i in range(3))
                break
        else:color=rgb[-1][1]
        ImageDraw.Draw(image).line((0,y,width,y),fill=color+(255,))
    return image


def paste_shape(canvas,draw_mask,stops):
    """Fill a shape (drawn white on a mask) with a vertical gradient."""
    mask=Image.new('L',canvas.size,0)
    draw_mask(ImageDraw.Draw(mask))
    box=mask.getbbox()
    fill=gradient((box[2]-box[0],box[3]-box[1]),stops)
    canvas.paste(fill,box[:2],mask.crop(box))


def render_unit():
    """A slim wall unit: soft white body, curved lower flap and a dark air outlet.

    Shading only, no outline, so it sits on light and dark pages alike."""
    s=SS
    unit=Image.new('RGBA',(1200*s,360*s),(0,0,0,0))
    left,right,top,seam,bottom=60*s,1140*s,8*s,285*s,352*s
    # Body: rounded top corners, sides flaring very slightly toward the seam.
    paste_shape(unit,lambda d:(d.rounded_rectangle((left+3*s,top,right-3*s,seam+20*s),radius=14*s,fill=255),
                               d.polygon([(left+3*s,top+40*s),(left,seam),(right,seam),(right-3*s,top+40*s)],fill=255),
                               d.rectangle((0,seam,unit.width,unit.height),fill=0)),
                [(0,'#e7e7e8'),(.22,'#fdfdfd'),(.45,'#fafafa'),(.7,'#eeeeef'),(1,'#dededf')])
    # Lower flap tapering inward, with rounded bottom corners.
    flap=lambda d:(d.polygon([(left,seam),(right,seam),(right-12*s,bottom-18*s),(left+12*s,bottom-18*s)],fill=255),
                   d.rounded_rectangle((left+12*s,seam+20*s,right-12*s,bottom),radius=18*s,fill=255))
    paste_shape(unit,flap,[(0,'#f8f8f7'),(.3,'#e8e8e8'),(.7,'#c6c5c6'),(1,'#d6d5d2')])
    # Louvre panel set into the flap, its sides curving in toward the outlet.
    depth=bottom-12*s-seam
    side=lambda x0,direction:[(x0+direction*14*s*(t/24)**2.5,seam+depth*t/24) for t in range(25)]
    left_side,right_side=side(150*s,1),side(1050*s,-1)
    paste_shape(unit,lambda d:d.polygon(left_side+right_side[::-1],fill=255),[(0,'#fbfaf9'),(.5,'#ecebeb'),(1,'#cfcecf')])
    draw=ImageDraw.Draw(unit)
    for points in (left_side,right_side):
        draw.line(points,fill='#8a8889',width=3*s,joint='curve')
    # Air outlet and the seam between body and flap.
    draw.rounded_rectangle((164*s,bottom-17*s,1036*s,bottom-10*s),radius=3*s,fill='#77787a')
    draw.line((left,seam,right,seam),fill='#cfcfd0',width=2*s)
    # A soft contact shadow, not an outline: it separates the white unit from
    # light pages and disappears on dark ones.
    shadow=Image.new('RGBA',unit.size,(40,40,36,0))
    shadow.putalpha(unit.getchannel('A').point(lambda a:a*34//255).filter(ImageFilter.GaussianBlur(7*s)))
    shadow=Image.alpha_composite(Image.new('RGBA',unit.size,(0,0,0,0)),shadow.transform(unit.size,Image.Transform.AFFINE,(1,0,0,0,1,-4*s)))
    return Image.alpha_composite(shadow,unit).resize((1200,360),Image.Resampling.LANCZOS)


def main():
    ASSETS.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGBA',(512,512),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((12,12,500,500),radius=112,fill='#18201c',outline='#748875',width=8)
    draw.arc((95,95,417,417),35,165,fill='#a7c9db',width=18)
    draw.arc((95,95,417,417),215,345,fill='#dbbd99',width=18)
    for y,end in [(216,326),(256,349),(296,309)]:
        draw.line((150,y,end-16,y),fill='#e8eddf',width=14)
        draw.arc((end-36,y-31,end+9,y+4),0,190,fill='#e8eddf',width=12)
    image.save(ASSETS/'app-icon.png')
    image.resize((52,52),Image.Resampling.LANCZOS).save(ASSETS/'app-mark.png')
    image.save(ASSETS/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    render_unit().save(ASSETS/'unit.png')


if __name__=='__main__':main()
