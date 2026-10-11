"""Render this project's original geometric artwork; no third-party images."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'src'/'room_ac_control'/'assets'


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
    unit=Image.new('RGBA',(1200,360),(0,0,0,0))
    draw=ImageDraw.Draw(unit)
    draw.rounded_rectangle((23,31,1177,329),radius=40,fill='#e8ebe5',outline='#bdc5b9',width=4)
    draw.rounded_rectangle((38,40,1162,271),radius=30,fill='#f5f6f0')
    draw.line((62,62,1138,62),fill='#ffffff',width=5)
    draw.rounded_rectangle((70,273,1130,313),radius=10,fill='#303c33')
    for x in range(96,1120,24):draw.line((x,281,x-4,305),fill='#899889',width=3)
    draw.line((83,296,1120,296),fill='#4a5a4c',width=3)
    draw.ellipse((1054,230,1064,240),fill='#94b891')
    unit.save(ASSETS/'unit.png')


if __name__=='__main__':main()
