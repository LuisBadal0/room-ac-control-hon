"""Render this project's original geometric artwork; no third-party images."""
import math
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


def render_icon(size=1024):
    """The app icon: the dashboard's cool-to-heat dial ring with two gusts of wind, on charcoal.

    Drawn at 1024 px; Windows' 16-48 px sizes are scaled down from it."""
    rgb=lambda value:tuple(int(value[i:i+2],16) for i in (1,3,5))
    image=Image.new('RGBA',(size,size),(0,0,0,0))
    ImageDraw.Draw(image).rounded_rectangle((40,40,size-40,size-40),radius=230,fill='#0e1116')
    ring,width=(190,190,size-190,size-190),80
    start,end=135,405  # Open at the bottom, like the dial.
    centre,radius=size/2,(ring[2]-ring[0])/2-width/2
    # A soft glow behind the ring.
    mask=Image.new('L',image.size,0)
    ImageDraw.Draw(mask).arc(ring,start,end,fill=255,width=width)
    glow=mask.filter(ImageFilter.GaussianBlur(70)).point(lambda a:int(a*.35))
    image.paste(Image.new('RGBA',image.size,rgb('#8fb4ff')+(255,)),(0,0),glow)
    # The ring runs from Cool blue through teal to Heat amber, with round ends.
    stops=[rgb('#5cc8ff'),rgb('#8fe3d0'),rgb('#ff9f43')]
    def colour(t):
        segment=t*(len(stops)-1)
        low=min(int(segment),len(stops)-2)
        k=segment-low
        return tuple(round(stops[low][i]+(stops[low+1][i]-stops[low][i])*k) for i in range(3))
    steps=120
    for index in range(steps):
        a0=start+(end-start)*index/steps
        a1=start+(end-start)*(index+1.4)/steps
        piece=Image.new('L',image.size,0)
        ImageDraw.Draw(piece).arc(ring,a0,a1,fill=255,width=width)
        image.paste(Image.new('RGBA',image.size,colour(index/(steps-1))+(255,)),(0,0),piece)
    draw=ImageDraw.Draw(image)
    for angle,t in ((start,0),(end,1)):
        x=centre+radius*math.cos(math.radians(angle))
        y=centre+radius*math.sin(math.radians(angle))
        draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=colour(t)+(255,))
    # Two gusts blowing left to right: the top one curls up, the bottom one down.
    ink,stroke=rgb('#e8ecf1')+(255,),52
    for x0,x1,y,r,up in ((330,610,460,50,True),(360,600,590,48,False)):
        draw.line(((x0,y),(x1,y)),fill=ink,width=stroke)
        draw.ellipse((x0-stroke/2,y-stroke/2,x0+stroke/2,y+stroke/2),fill=ink)
        if up:
            draw.arc((x1-r-stroke/2,y-2*r-stroke/2,x1+r+stroke/2,y+stroke/2),180,450,fill=ink,width=stroke)
            tip=(x1-r,y-r)
        else:
            draw.arc((x1-r-stroke/2,y-stroke/2,x1+r+stroke/2,y+2*r+stroke/2),270,540,fill=ink,width=stroke)
            tip=(x1-r,y+r)
        draw.ellipse((tip[0]-stroke/2,tip[1]-stroke/2,tip[0]+stroke/2,tip[1]+stroke/2),fill=ink)
    return image


def main(unit=True):
    ASSETS.mkdir(parents=True,exist_ok=True)
    icon=render_icon()
    icon.resize((512,512),Image.Resampling.LANCZOS).save(ASSETS/'app-icon.png')
    icon.resize((52,52),Image.Resampling.LANCZOS).save(ASSETS/'app-mark.png')
    icon.resize((256,256),Image.Resampling.LANCZOS).save(ASSETS/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    if unit:
        render_unit().save(ASSETS/'unit.png')


if __name__=='__main__':main(unit='--icon-only' not in __import__('sys').argv)
