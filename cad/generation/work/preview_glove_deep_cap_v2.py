from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
m=np.load('work/glove_deep_cap_v2_meshes.npz')
im=Image.new('RGB',(1600,1100),'#f2f5f8');d=ImageDraw.Draw(im)
def txt(x,y,text,size=23,color='#21394a',bold=False):
    font=ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),size)
    d.text((x,y),text,font=font,fill=color)
def render(t,centre,scale,color):
    v=np.array([.65,-1.1,1.75]);v/=np.linalg.norm(v)
    r=np.cross([0,0,1],v);r/=np.linalg.norm(r);u=np.cross(v,r)
    mid=(t.min((0,1))+t.max((0,1)))/2
    n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    facing=n@v;mask=facing>1e-6;t=t[mask];facing=facing[mask]
    uv=np.stack(((t-mid)@r,-(t-mid)@u),axis=-1)*scale+centre
    colors=((.55+.45*facing[:,None])*np.array(color)).astype(int)
    for i in np.argsort(t.mean(axis=1)@v):d.polygon([tuple(p) for p in uv[i]],fill=tuple(colors[i]))
txt(40,28,'Glove cap v2: deeper outside overlap',36,bold=True)
txt(40,84,'Replacement cap for your existing sewn base. Same fit, openings and internal stops.',23)
for x in [35,815]:d.rounded_rectangle((x,140,x+750,690),radius=20,fill='white')
txt(65,165,'CURRENT CAP',24,bold=True,color='#69737a')
txt(845,165,'REVISED CAP',24,bold=True,color='#176f9b')
render(m['old_cap'],(410,405),5.0,(150,160,169))
render(m['cap'],(1190,405),5.0,(50,145,192))
txt(65,610,'5 mm overlap',30,bold=True,color='#69737a')
txt(845,610,'14 mm overlap  /  2.8x deeper',30,bold=True,color='#176f9b')
txt(845,652,'Skirt wraps outside the existing base.',20)

d.rounded_rectangle((35,720,1565,1030),radius=20,fill='white')
txt(65,745,'CLOSED-SIDE CROSS-SECTION (SCHEMATIC)',22,bold=True)
# The drawing shows one wall and the assembled vertical dimensions; it is not
# a section of the vent, wire opening or electronics.
scale=10;left=100;right=485;top=815;bottom=top+18.8*scale
d.rectangle((left,top,right,bottom),fill='#e2e9ed',outline='#7c929f',width=2)
d.rectangle((left+18,top,right-18,bottom-18),fill='white')
d.rectangle((left-17.5,top-16,right+17.5,top),fill='#3192c0')
for a,b in [(left-17.5,left-1.5),(right+1.5,right+17.5)]:d.rectangle((a,top,b,top+14*scale),fill='#3192c0')
txt(600,823,'14 mm of engagement along closed walls',25,bold=True,color='#176f9b')
txt(600,868,'4.8 mm clearance above the glove / base underside',23)
txt(600,912,'Wire and USB/battery notches remain open.',23)
txt(600,956,'Base sewing holes, vents and anti-tilt stops retained.',23)
txt(40,1057,'Cap only: 59.7 x 68.1 x 15.6 mm. Longer friction fit; physical retention still needs a test print.',21)
im.save('outputs/Glove_housing_cap_v2_preview.png')
print(Path('outputs/Glove_housing_cap_v2_preview.png').resolve())
