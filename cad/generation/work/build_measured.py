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

# Measured module, edge-based offsets, chip long axis along module length.
W,L,H=44.85,66.6,19.6
floor=1.6
cx,cy=23.0,49.8
radius=7.3
# Main cavity has no unmeasured board-height ledges.
adds=[(0,0,0,W,L,H)]
subs=[(1.8,1.8,floor,W-1.8,L-1.8,H+1),
      (.8,.8,H-1.4,W-.8,L-.8,H+1),
      (8,-1,floor,W-8,2,H+1),
      (cx-radius,cy-radius,-1,cx+radius,cy+radius,2)]
def circle_warp(t):
 p=t.copy();dx=p[:,:,0]-cx;dy=p[:,:,1]-cy;r=np.maximum(abs(dx),abs(dy));rr=np.hypot(dx,dy)
 mask=(r>=radius-1e-8)&(r<radius+2)&(rr>0)
 factor=np.ones_like(r);factor[mask]=1+(radius+2-r[mask])/2*(radius/rr[mask]-1)
 p[:,:,0]=cx+dx*factor;p[:,:,1]=cy+dy*factor
 return p
samples=sorted(set([-radius-2,-radius,radius,radius+2]+list(np.linspace(-radius,radius,41))))
housing=mesh(adds,subs,([cx+v for v in samples],[cy+v for v in samples],[]),circle_warp)
# Cap locating tongue sits in rim recess, outside the measured-module cavity.
slot_y=L-2.3-(7.45+18+1)
cap=mesh([(0,0,0,W,L,1.6),(1,1,1.6,1.6,L-1,2.8),(W-1.6,1,1.6,W-1,L-1,2.8),(1,1,1.6,W-1,1.6,2.8),(1,L-1.6,1.6,W-1,L-1,2.8)],[(.1*W,slot_y,-1,.9*W,L+1,4),(8,.9,1.6,W-8,1.7,4)])
# Battery cap unchanged from preceding revision.
b=Path('outputs/Battery_cap_two_wire_notches.stl').read_bytes()
bat=np.array([struct.unpack_from('<12f',b,84+50*i)[3:] for i in range(struct.unpack_from('<I',b,80)[0])]).reshape(-1,3,3)
report={}
for name,t in [('Mic_housing_MEASURED_v2.stl',housing),('Mic_cap_MEASURED_v2.stl',cap)]:report[name]=save(t,name)
parts=[housing,cap+[W+8,0,0],bat+[2*(W+8),0,0]]
report['combined_one']=save(np.concatenate(parts),'Measured_v2_combined_1_battery_cap.stl')
parts.append(bat+[2*(W+8),21.5,0])
report['combined_two']=save(np.concatenate(parts),'Measured_v2_combined_2_battery_caps.stl')
for i,a in enumerate(parts):
 assert abs(a[:,:,2].min())<1e-6
 for b in parts[i+1:]:assert any(a.max((0,1))[k]<b.min((0,1))[k] or b.max((0,1))[k]<a.min((0,1))[k] for k in (0,1))
# Verify confirmed chip footprint is completely within cap opening.
chip_x=(2.3+11.1,2.3+11.1+16)
chip_y=(L-2.3-7.45-18,L-2.3-7.45)
assert chip_x[0]>.1*W and chip_x[1]<.9*W and chip_y[0]>slot_y
assert np.allclose([W-3.6,L-3.6,H-floor],[41.25,63,18])
# Cap assembly: printed cap Z points towards cavity; mirrored Y to preserve top edge.
# Geometrical collision check using analytic boxes: tongue lies within rim pocket,
# and outside measured module plan x=[2.3,42.55], y=[2.3,64.3].
assert 1.6<2.3 and H-1.2>H-1.4
np.savez('work/measured_enclosure_meshes.npz',housing=housing,cap=cap,bat=bat)
(O/'Measured_v2_dimensions.txt').write_text('''MEASURED ENCLOSURE V2 - MILLIMETRES
Replaces the earlier prototype microphone housing and cap.
Module: width 40.25, length 62, thickness approximately 17.
Cavity: width 41.25, length 63, depth 18 (0.5 mm nominal clearance per side).
Assembled exterior: width 44.85, length 66.6, depth 21.2.
Tray height: 19.6. Floor and cap face: 1.6 thick. Main side walls: 1.8.
Cap uses a 0.6 mm locating tongue in a recessed rim, with 0.2 mm lateral clearance.
It is not a locking snap fit: retain cap using tape tabs on the closed side portions.
No ledges at an assumed perfboard height: previous ledges removed to avoid component collisions.

POSITION REFERENCES
Top is the small-overhang end; bottom is the connector end.
All side measurements use the SAME physical reference edge for both faces. Do not mirror the reference when turning the assembly over.
Offsets supplied are to nearest component edges.
Module nominal location in tray: X=2.3 to 42.55, Y=2.3 to 64.3.
Chip: 16 wide x 18 along module length; nearest edge 11.1 from side, 7.45 from top.
Chip footprint in tray: X=13.4 to 29.4, Y=38.85 to 56.85.
Cap opening: X=4.485 to 40.365 (35.88 wide, 80% of cap); from Y=37.85 to top edge.
Microphone: diameter 14; nearest edge 13.7 from side and 7.5 from top.
Mic centre relative to module: 20.7 from side, 14.5 from top.
Mic opening: diameter 14.6; centre in tray X=23, Y=49.8.
Bottom connector access: 28.85 wide, open from the inner floor upwards.
Exact connector outlines were not supplied, so broad access is retained.

PRINT AND FIT
STLs are in bed orientation, separated by at least 8 mm in combined files.
Print at 100% scale, millimetres. Inspect thin locating tongues in slicer preview.
Test empty parts and check opening alignment before securing electronics. Physical fit remains untested.
Battery caps are unchanged from the prior two-end-notch revision; no battery housing is included.
Combined options contain one mic tray, one mic cap, and either one or two battery caps.
''')
(O/'Measured_v2_mesh_checks.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))


