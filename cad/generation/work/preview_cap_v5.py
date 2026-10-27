import numpy as np
from PIL import Image,ImageDraw,ImageFont
t=np.load('work/cap_v5_mesh.npy');im=Image.new('RGB',(1500,850),'#f3f6fa');d=ImageDraw.Draw(im)
def txt(x,y,s,n=22):d.text((x,y),s,font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n),fill='#183449')
def render(t,centre,scale,color,top=False):
 v=np.array([.7,1.2 if top else -1.2,1.8]);v/=np.linalg.norm(v);r=np.cross([0,0,1],v);r/=np.linalg.norm(r);u=np.cross(v,r);mid=(t.min((0,1))+t.max((0,1)))/2;f=[]
 for a in t:
  n=np.cross(a[1]-a[0],a[2]-a[0]);n/=np.linalg.norm(n)
  if n@v<=0:continue
  q=a-mid;uv=np.column_stack((q@r,-q@u))*scale+centre;shade=.55+.45*float(n@v)
  f.append((a.mean(0)@v,uv,tuple(int(x*shade) for x in color)))
 for _,uv,c in sorted(f,key=lambda q:q[0]):d.polygon([tuple(p) for p in uv],fill=c)

txt(40,28,'Revised cap: separate cooling and reset openings',32)
txt(40,78,'Solid bridge between openings; outer skirt and 11.6 mm stops retained.',23)
render(t,(400,430),8,(55,153,205))
render(t,(1100,430),8,(112,167,193),True)
txt(120,725,'Inside face: two stops over perfboard edges',22)
txt(835,725,'5 mm skirt wraps around case exterior',22)
txt(40,790,'Reset opening: 20 x 20 mm, centred across width. Solid bridge: 4.55 mm wide.',22)
im.save('outputs/Mic_cap_v5_preview.png')
