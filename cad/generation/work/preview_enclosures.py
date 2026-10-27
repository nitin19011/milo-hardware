import numpy as np
from PIL import Image,ImageDraw,ImageFont
m=np.load('work/enclosure_meshes.npz');im=Image.new('RGB',(1500,850),'#f3f6fa');d=ImageDraw.Draw(im)
def txt(x,y,s,n=22):d.text((x,y),s,font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n),fill='#183449')
def render(t,centre,scale,color):
 v=np.array([.7,-1.2,1.8]);v/=np.linalg.norm(v);r=np.cross([0,0,1],v);r/=np.linalg.norm(r);u=np.cross(v,r);mid=(t.min((0,1))+t.max((0,1)))/2;f=[]
 for a in t:
  n=np.cross(a[1]-a[0],a[2]-a[0]);n/=np.linalg.norm(n)
  if n@v<=0:continue
  q=a-mid;uv=np.column_stack((q@r,-q@u))*scale+centre;shade=.55+.45*float(n@v)
  f.append((a.mean(0)@v,uv,tuple(int(x*shade) for x in color)))
 for _,uv,c in sorted(f,key=lambda q:q[0]):d.polygon([tuple(p) for p in uv],fill=c)
txt(40,28,'Actual STL preview â€” microphone enclosure and revised battery cap',32)
txt(40,78,'Prototype dimensions: verify against your assembled electronics before printing.',22)
render(m['housing'],(295,425),7,(112,167,193))
render(m['cap'],(827,425),7,(55,153,205))
render(m['bat'],(1300,420),7,(66,160,161))
txt(85,710,'Mic housing: 44.4 Ã— 66.4 Ã— 23 mm',22)
txt(680,710,'Cap: 80%-width opening',22)
txt(1130,640,'Two end wire notches',22)
txt(40,785,'Parts shown separately in print orientation. Combined STL options include one or two battery caps.',22)
im.save('outputs/enclosure_print_preview.png')
