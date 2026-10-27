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



# Replacement cap only, matching existing necklace housing.
W,L,H=44.85,66.6,19.6
clearance=.15
wall=1.6
lip=5.0
stop_depth=11.6 # measured rim-to-board 11.8, with 0.2 clearance
# Model in print coordinates: outside face on Z=0, inside features upwards.
a=-clearance-wall
b=-clearance
X=W+clearance+wall
Y=L+clearance+wall
adds=[(a,a,0,X,Y,wall),
      (a,a,wall,b,Y,wall+lip),
      (W+clearance,a,wall,X,Y,wall+lip),
      (a,a,wall,X,b,wall+lip),
      (a,L+clearance,wall,X,Y,wall+lip),
      (2.0,54,wall,4.3,60,wall+stop_depth),
      (W-4.3,54,wall,W-2.0,60,wall+stop_depth)]
subs=[(.1*W,13.8,-1,.9*W,Y+1,wall+stop_depth+1),
      (8,a-1,wall,W-8,b+1,wall+lip+1)]
cap=mesh(adds,subs)
# Case-coordinate inspection checks.
assert 2.0>1.8 and 4.3<.1*W
assert 54>1.8 and 60<L-1.8
assert abs((H-stop_depth)-(H-11.8)-.2)<1e-8
assert L-2.3-41-13.8>=9
assert .8*W>=18
# Stops remain clear of the measured main chip in X.
assert 4.3<13.4 and W-4.3>29.4
# Outer overlap stops above necklace holes, which end at case Z=12.3.
assert H-lip>12.3
cap-=cap.min((0,1))
info=save(cap,'Mic_cap_v4_outer_skirt_RST_stops.stl')
np.save('work/cap_v4_mesh.npy',cap)
(O/'Mic_cap_v4_notes.txt').write_text("""REPLACEMENT CAP V4 - CAP ONLY
Fits existing necklace housing (nominal exterior 44.85 x 66.6 mm).
External skirt: 5 mm overlap, 0.15 mm clearance per side, 1.6 mm walls.
Overall printed cap: 48.35 x 70.10 x 13.20 mm including inward stops.
Outer face is already on print bed, Z=0; print at 100% in millimetres.

OPENING
Wide top opening: 35.88 mm; reaches 50.5 mm from module top.
RST centre: 41 mm from module top. Opening extends 9.5 mm below RST centre.
Finger access is at least 18 mm in both directions around the longitudinal RST position;
button lateral position has not been supplied, so the opening spans 80% of housing width.
Chip cooling and top wire access retained.

ANTI-TILT STOPS
Two 2.3 x 6 mm contact faces over the left/right perfboard edge regions near the top.
Inward projection: 11.6 mm from the cap underside, using measured 11.8 mm rim-to-board distance.
Nominal gap above seated perfboard: 0.2 mm. Stops limit lift instead of preloading the board.
Contact regions in existing case coordinates:
left X=2.0..4.3, right X=40.55..42.85, both Y=54..60.
Their positions assume these narrow perfboard edge strips are clear of wires/components.
Before seating, confirm both stops land on bare perfboard. Do not force the cap over an obstruction.

FIT
Cap wraps outside the existing printed housing; no new bottom case is required.
The bottom connector relief and the two necklace holes remain accessible.
External fit is printer-dependent and not physically tested; verify grip before wearing.
This is a friction sleeve, not a positive-locking latch. Add tape tabs if needed.
Mesh checked for closed edges, consistent winding, positive volume and nondegenerate triangles.
""")
(O/'Mic_cap_v4_checks.json').write_text(json.dumps(info,indent=2))
print(json.dumps(info,indent=2))
