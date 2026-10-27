import struct, collections, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
OUT=Path('outputs'); OUT.mkdir(exist_ok=True)
b=Path('inputs/LiPo_600mAh_slide_sleeve.stl').read_bytes()
sleeve=np.array([struct.unpack_from('<12f',b,84+50*i)[3:] for i in range(struct.unpack_from('<I',b,80)[0])]).reshape(-1,3,3)
# Exact rectilinear boundary mesh, subdivided consistently to avoid T-junctions.
def cap(c):
 xs=sorted(set([-c-1.6,-c,11.1,17.1,28.2+c,28.2+c+1.6]))
 ys=[-1.6,0,8]
 zs=[-c-1.6,-c,4.95,9.9+c,9.9+c+1.6]
 def solid(x,y,z):
  shell=(y<0 or x<-c or x>28.2+c or z<-c or z>9.9+c)
  notch=11.1<x<17.1 and z>4.95
  return shell and not notch
 filled=set()
 for i in range(len(xs)-1):
  for j in range(len(ys)-1):
   for k in range(len(zs)-1):
    if solid((xs[i]+xs[i+1])/2,(ys[j]+ys[j+1])/2,(zs[k]+zs[k+1])/2): filled.add((i,j,k))
 tris=[]
 for i,j,k in filled:
  x,X=xs[i:i+2]; y,Y=ys[j:j+2]; z,Z=zs[k:k+2]
  faces=[((-1,0,0),[(x,y,z),(x,y,Z),(x,Y,Z),(x,Y,z)]),((1,0,0),[(X,y,z),(X,Y,z),(X,Y,Z),(X,y,Z)]),((0,-1,0),[(x,y,z),(X,y,z),(X,y,Z),(x,y,Z)]),((0,1,0),[(x,Y,z),(x,Y,Z),(X,Y,Z),(X,Y,z)]),((0,0,-1),[(x,y,z),(x,Y,z),(X,Y,z),(X,y,z)]),((0,0,1),[(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)])]
  for (di,dj,dk),q in faces:
   if (i+di,j+dj,k+dk) not in filled:
    tris.extend([[q[0],q[1],q[2]],[q[0],q[2],q[3]]])
 return np.array(tris)
def save(t,path):
 # Print on end face: model X,Y,Z -> print X,-Z,Y; proper rotation.
 p=t[:,:,[0,2,1]].copy(); p[:,:,1]*=-1; p-=p.min(axis=(0,1))
 edges=collections.Counter()
 for a in p:
  for v,w in zip(a,np.roll(a,-1,axis=0)): edges[tuple(sorted((tuple(v.round(6)),tuple(w.round(6)))))] +=1
 assert set(edges.values())=={2},set(edges.values())
 volume=np.einsum('ij,ij->i',p[:,0],np.cross(p[:,1],p[:,2])).sum()/6
 assert volume>0
 with path.open('wb') as f:
  f.write(b'Milo battery external cap; millimetres'.ljust(80,b' ')); f.write(struct.pack('<I',len(p)))
  for a in p:
   n=np.cross(a[1]-a[0],a[2]-a[0]); n/=np.linalg.norm(n)
   f.write(struct.pack('<12fH',*n,*a.flatten(),0))
 return {'triangles':len(p),'closed_mesh':True,'volume_mm3':round(volume,2),'print_dimensions_mm':p.max(axis=(0,1)).round(3).tolist()}
report={}
for name,c in [('standard',.2),('looser',.35)]: report[name]=save(cap(c),OUT/f'LiPo_600mAh_cap_{name}.stl')
(OUT/'LiPo_600mAh_cap.scad').write_text('''// Matching external cap for the supplied sleeve; units: mm.
// Exported STLs are already oriented with the end face on the print bed.
clearance = 0.20; // per side; looser version uses 0.35
wall = 1.6;
overlap = 8;
wire_width = 6;
module cap() {
 difference() {
  translate([-clearance-wall,-wall,-clearance-wall])
   cube([28.2+2*(clearance+wall),overlap+wall,9.9+2*(clearance+wall)]);
  translate([-clearance,0,-clearance])
   cube([28.2+2*clearance,overlap+1,9.9+2*clearance]);
  translate([(28.2-wire_width)/2,-wall-1,4.95])
   cube([wire_width,overlap+wall+2,10]);
 }
}
translate([clearance+wall,9.9+clearance+wall,wall]) rotate([90,0,0]) cap();
''')
# Orthographic mesh preview; render actual model triangles.
im=Image.new('RGB',(1500,950),'#f3f6fa'); d=ImageDraw.Draw(im)
fontpath=r'C:\Windows\Fonts\arial.ttf'
f=ImageFont.truetype(fontpath,25); small=ImageFont.truetype(fontpath,20); title=ImageFont.truetype(fontpath,34)
d.text((45,25),'Battery sleeve + removable end cap',font=title,fill='#173047')
d.text((45,75),'Original sleeve in grey  |  New cap in blue  |  Dimensions assumed to be millimetres',font=small,fill='#506477')
def render(items,center,scale):
 view=np.array([.7,-1.3,1.0]); view/=np.linalg.norm(view)
 right=np.cross([0,0,1],view); right/=np.linalg.norm(right); up=np.cross(view,right)
 allp=np.concatenate([t.reshape(-1,3) for t,c in items]); mid=(allp.min(0)+allp.max(0))/2
 faces=[]
 for t,col in items:
  for tri in t:
   n=np.cross(tri[1]-tri[0],tri[2]-tri[0]); n/=np.linalg.norm(n)
   if n@view<=0: continue
   pts=tri-mid; uv=np.column_stack((pts@right,-pts@up))*scale+center
   shade=.6+.4*max(0,float(n@view)); color=tuple(int(v*shade) for v in col)
   faces.append((float(tri.mean(0)@view),uv,color))
 for depth,uv,col in sorted(faces,key=lambda x:x[0]): d.polygon([tuple(p) for p in uv],fill=col)
render([(sleeve,(180,193,203)),(cap(.2)+[0,-12,0],(45,155,218))],(390,450),12)
render([(cap(.2),(45,155,218))],(1130,440),19)
d.text((90,770),'Exploded view: cap slides onto the open end',font=f,fill='#173047')
d.text((880,670),'6 mm top-opening wire notch',font=f,fill='#173047')
d.text((880,715),'8 mm overlap; 1.6 mm walls',font=small,fill='#506477')
d.text((880,750),'0.20 mm clearance on each side',font=small,fill='#506477')
d.text((90,850),'Prototype fit: test on the empty sleeve first. Secure with a tape tab if needed.',font=f,fill='#173047')
im.save(OUT/'battery_cap_preview.png')
print(json.dumps(report,indent=2))
