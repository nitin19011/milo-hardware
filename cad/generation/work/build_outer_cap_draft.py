import struct, collections, json
from pathlib import Path
import numpy as np
O=Path('outputs')
def mesh(add,sub=[],extra=([],[],[]),warp=None):
 axes=[sorted(set([b[k] for b in add+sub]+[b[k+3] for b in add+sub]+list(extra[k]))) for k in range(3)]
 def inside(p,b): return all(b[k]<p[k]<b[k+3] for k in range(3))
 cells=set()
 for i in range(len(axes[0])-1):
  for j in range(len(axes[1])-1):
   for k in range(len(axes[2])-1):
    p=[(axes[a][q]+axes[a][q+1])/2 for a,q in enumerate((i,j,k))]
    if any(inside(p,b) for b in add) and not any(inside(p,b) for b in sub): cells.add((i,j,k))
 ts=[]
 for i,j,k in cells:
  x,X=axes[0][i:i+2];y,Y=axes[1][j:j+2];z,Z=axes[2][k:k+2]
  faces=[((-1,0,0),[(x,y,z),(x,y,Z),(x,Y,Z),(x,Y,z)]),((1,0,0),[(X,y,z),(X,Y,z),(X,Y,Z),(X,y,Z)]),((0,-1,0),[(x,y,z),(X,y,z),(X,y,Z),(x,y,Z)]),((0,1,0),[(x,Y,z),(x,Y,Z),(X,Y,Z),(X,Y,z)]),((0,0,-1),[(x,y,z),(x,Y,z),(X,Y,z),(X,y,z)]),((0,0,1),[(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)])]
  for (di,dj,dk),q in faces:
   if (i+di,j+dj,k+dk) not in cells: ts.extend([[q[0],q[1],q[2]],[q[0],q[2],q[3]]])
 t=np.array(ts,float)
 if warp: t=warp(t)
 return t

def validate(t):
 edges=collections.Counter(); directed=collections.Counter()
 for a in np.round(t,6):
  for v,w in zip(a,np.roll(a,-1,axis=0)):
   v,w=tuple(v),tuple(w); edges[tuple(sorted((v,w)))]+=1; directed[(v,w)]+=1
 assert set(edges.values())=={2},collections.Counter(edges.values())
 assert all(directed[(w,v)]==n for (v,w),n in directed.items())
 area=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
 assert area.min()>1e-8
 volume=np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6
 assert volume>0
 return {'triangles':len(t),'closed_consistent_mesh':True,'volume_mm3':round(volume,2),'size_mm':(t.max((0,1))-t.min((0,1))).round(3).tolist()}
def save(t,name):
 info=validate(t)
 with (O/name).open('wb') as f:
  f.write(b'Milo prototype enclosure; units millimetres'.ljust(80,b' '));f.write(struct.pack('<I',len(t)))
  for a in t:
   n=np.cross(a[1]-a[0],a[2]-a[0]);n/=np.linalg.norm(n);f.write(struct.pack('<12fH',*n,*a.flatten(),0))
 return info


# Preliminary outer cap geometry only. Reset opening / anti-tilt contacts pending measurements.
# Original housing remains 44.85 x 66.6 mm. 0.15 mm clearance per side.
W,L=44.85,66.6
clearance=.15
wall=1.6
lip=5.0
# Print outside face down, sleeve walls upwards.
a=-clearance-wall
b=-clearance
X=W+clearance+wall
Y=L+clearance+wall
adds=[(a,a,0,X,Y,wall),
      (a,a,wall,b,Y,wall+lip),
      (W+clearance,a,wall,X,Y,wall+lip),
      (a,a,wall,X,b,wall+lip),
      (a,L+clearance,wall,X,Y,wall+lip)]
subs=[(.1*W,37.85,-1,.9*W,Y+1,wall+lip+1),
      (8,a-1,wall,W-8,b+1,wall+lip+1)]
cap=mesh(adds,subs)
info=validate(cap)
np.save('work/outer_cap_pending_reset_and_stops.npy',cap)
Path('work/outer_cap_plan.txt').write_text(str(info)+'\n5 mm external overlap; opening and stopper geometry pending actual reset/PCB measurements.')
print(info)
