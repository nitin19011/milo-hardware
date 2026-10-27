import numpy as np
from PIL import Image,ImageDraw,ImageFont
m=np.load('work/battery_flush_meshes.npz');im=Image.new('RGB',(1500,850),'#f3f6fa');d=ImageDraw.Draw(im)
def txt(x,y,s,n=23,c='#19364b'):d.text((x,y),s,font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n),fill=c)
def render(items,centre,scale):
 v=np.array([.7,-1.2,1.3]);v/=np.linalg.norm(v);r=np.cross([0,0,1],v);r/=np.linalg.norm(r);u=np.cross(v,r)
 allp=np.concatenate([t for t,c in items]);mid=(allp.min((0,1))+allp.max((0,1)))/2;faces=[]
 for t,color in items:
  for a in t:
   n=np.cross(a[1]-a[0],a[2]-a[0]);n/=np.linalg.norm(n)
   if n@v<=0:continue
   q=a-mid;uv=np.stack((q@r,-q@u),axis=1)*scale+centre
   col=tuple(int(z*(.55+.45*(n@v))) for z in color)
   faces.append((a.mean(0)@v,uv,col))
 for _,uv,col in sorted(faces,key=lambda a:a[0]):d.polygon([tuple(p) for p in uv],fill=col)
txt(40,30,'Battery holder with a flush underside',35)
txt(40,85,'Original battery space preserved; redesigned cap fits over the sides and top.',23)
render([(m['base'],(168,184,197)),(m['cap'],(48,152,205))],(395,430),12)
txt(200,710,'Assembled holder',24)
# Exact side outline of assembled part, longitudinal cross-sectional silhouette.
ox,basey,s=845,510,13
def box(y0,z0,y1,z1,col):d.rectangle((ox+y0*s,basey-z1*s,ox+y1*s,basey-z0*s),fill=col)
box(0,0,39,9.9,'#a8b8c5')
box(-1.6,0,0,11.7,'#3098cd')
box(0,10.1,8,11.7,'#3098cd')
# side cap wall visible in elevation
box(0,0,8,11.7,'#3098cd')
d.line([(805,basey+3),(1385,basey+3)],fill='#138078',width=4)
txt(915,264,'SIDE VIEW',25)
txt(847,320,'Cap',23,c='#227eac');txt(1140,350,'Original base',23)
txt(893,545,'Both bottoms lie on the same plane',23,c='#138078')
txt(839,609,'Cap overlap: 8 mm',22)
txt(839,645,'No cap skirt underneath the base',22)
txt(40,789,'Separate base and cap, plus a combined print file. Slip-fit cap; physical fit remains untested.',22)
im.save('outputs/Battery_flush_preview.png')
