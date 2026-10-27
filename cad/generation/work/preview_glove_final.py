import numpy as np
from PIL import Image,ImageDraw,ImageFont
m=np.load('work/glove_final_meshes.npz')
im=Image.new('RGB',(1650,1020),'#f3f6fa');d=ImageDraw.Draw(im)
def txt(x,y,s,n=23):d.text((x,y),s,font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n),fill='#19364b')
def render(t,centre,scale,color):
 v=np.array([.65,-1.1,2]);v/=np.linalg.norm(v);r=np.cross([0,0,1],v);r/=np.linalg.norm(r);u=np.cross(v,r)
 mid=(t.min((0,1))+t.max((0,1)))/2
 n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
 facing=n@v;mask=facing>1e-6;t=t[mask];facing=facing[mask]
 uv=np.stack(((t-mid)@r,-(t-mid)@u),axis=-1)*scale+centre
 colors=((.55+.45*facing[:,None])*np.array(color)).astype(int)
 depths=t.mean(axis=1)@v
 for i in np.argsort(depths):d.polygon([tuple(q) for q in uv[i]],fill=tuple(colors[i]))
txt(40,30,'Glove enclosure â€” final STL preview',34)
txt(40,85,'12 internal stitch pairs  |  IMU pocket  |  Outer-fitting cap with three openings and four stops',23)
render(m['base'],(405,482),8.1,(108,161,186))
render(m['cap'],(1210,482),8.1,(55,151,201))
txt(115,817,'Base: 56.2 x 64.6 x 18.8 mm',25)
txt(918,817,'Cap shown outer face down for printing',25)
txt(90,880,'Sew the empty base to the glove first.',23)
txt(916,880,'Flip cap over to align the IMU pocket.',23)
txt(40,954,'Measured assembly: 40 x 60 x 16 mm; IMU overhang 11.6 mm. Physical fit still requires a test print.',22)
im.save('outputs/Glove_housing_v1_preview.png')
