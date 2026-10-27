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
# Assumed: 40x60 board, 2 mm top overhang, 1.6 mm board thickness.
W,L,H=44.4,66.4,23.0
cx,cy=22.2,54.8
adds=[(0,0,0,W,L,1.6),(0,0,0,1.8,L,H),(W-1.8,0,0,W,L,H),(0,0,0,W,1.8,H),(0,L-1.8,0,W,L,H), (1.8,4,8,2.6,61.8,9),(41.8,4,8,42.6,61.8,9)]
subs=[(8,-1,10.6,36.4,2,H+1),(cx-5,cy-5,-1,cx+5,cy+5,2)]
def circle_warp(t):
 p=t.copy();dx=p[:,:,0]-cx;dy=p[:,:,1]-cy;r=np.maximum(abs(dx),abs(dy));rr=np.hypot(dx,dy)
 mask=(r>=5-1e-8)&(r<7)&(rr>0)
 factor=np.ones_like(r);factor[mask]=1+(7-r[mask])/2*(5/rr[mask]-1)
 p[:,:,0]=cx+dx*factor;p[:,:,1]=cy+dy*factor
 return p
housing=mesh(adds,subs,([cx+v for v in np.arange(-7,7.01,.5)],[cy+v for v in np.arange(-7,7.01,.5)],[]),circle_warp)
# Removable cap: printed outside face down; 3 mm internal locating skirt.
cap=mesh([(0,0,0,W,L,1.6),(2,2,1.6,3.2,64.4,4.6),(41.2,2,1.6,42.4,64.4,4.6),(2,2,1.6,42.4,3.2,4.6),(2,63.2,1.6,42.4,64.4,4.6)],[(.1*W,32,-1,.9*W,L+1,6),(8,1.9,1.6,36.4,3.3,6)])
# Existing sleeve end cap, revised only: two edge-adjacent wire notches.
c=.2;wall=1.6
bat=mesh([(-c-wall,-wall,-c-wall,28.2+c+wall,8,9.9+c+wall)],[(-c,0,-c,28.2+c,9,9.9+c),(1.2,-2,4.95,7.2,9,12),(21,-2,4.95,27,9,12)])
bat=bat[:,:,[0,2,1]].copy();bat[:,:,1]*=-1;bat-=bat.min((0,1))
report={}
for name,t in [('Mic_housing_PROTOTYPE.stl',housing),('Mic_open_cap_PROTOTYPE.stl',cap),('Battery_cap_two_wire_notches.stl',bat)]:report[name]=save(t,name)
# All components kept separate, floor/end faces on bed.
parts=[housing,cap+[52.4,0,0],bat+[104.8,0,0]]
report['combined_one_battery_cap']=save(np.concatenate(parts),'Mic_housing_and_caps_1_battery_cap.stl')
parts.append(bat+[104.8,21.5,0])
report['combined_two_battery_caps']=save(np.concatenate(parts),'Mic_housing_and_caps_2_battery_caps.stl')
for i,a in enumerate(parts):
 assert abs(a[:,:,2].min())<1e-6
 for b in parts[i+1:]:assert any(a.max((0,1))[k]<b.min((0,1))[k] or b.max((0,1))[k]<a.min((0,1))[k] for k in (0,1))
(O/'Enclosure_print_notes.txt').write_text('''PROTOTYPE - CHECK DIMENSIONS BEFORE PRINTING
Units: millimetres. Models already have intended bed faces at Z=0.

MIC HOUSING
External assembled dimensions: 44.4 wide x 66.4 long x 24.6 deep.
Internal plan: 40.8 x 62.8. Assumes approximately 2 mm ESP overhang at TOP.
Board mic-side face sits 9 mm above the outer floor (7.4 mm clear space above inner floor).
Assumed perfboard thickness: 1.6 mm. ESP-side clearance: 12.4 mm to cap underside.
Edge ledges support the board; cap does not positively clamp it. Add removable spacers on unused board edges if needed.
Circular mic opening: 10 mm diameter, centre at X=22.2, Y=54.8 from bottom-left outer corner.
Bottom connector opening: 28.4 mm wide; starts 10.6 mm above outer floor.
Cap top-opening slot: 35.52 mm wide (80% of cap), 34.4 mm long.
Cap uses a locating skirt with 0.2 mm side clearance, NOT a snap latch. Retain with tape tabs along closed side sections.
Component, microphone and connector locations have NOT been measured from the real assembly.

BATTERY CAP
Fits original 28.2 x 9.9 mm sleeve end with 0.2 mm clearance per side; overlap 8 mm.
Two 6 mm-wide notches near opposite ends replace the previous centre notch.
Original battery housing is unchanged and is NOT included in either combined print.
Secure cap with tape if loose; smooth wire-contact edges before use.

COMBINED FILES
Mic_housing_and_caps_1_battery_cap.stl: 1 mic tray + 1 mic cap + 1 battery cap.
Mic_housing_and_caps_2_battery_caps.stl: 1 mic tray + 1 mic cap + 2 battery caps.
All parts are separate within a single STL, with 8 mm minimum planar spacing.
Check the slicer preview, especially the internal board-support ledges; supports may be needed depending on printer settings.
Test fit empty parts before putting electronics or the battery inside. Do not force an undersized enclosure over components.
Mesh checks: closed edges, consistent winding, nonzero triangle areas, positive volume, parts separated and resting on bed.
These checks do not establish physical fit or cooling performance.
''')
(O/'enclosure_mesh_checks.json').write_text(json.dumps(report,indent=2))
np.savez('work/enclosure_meshes.npz',housing=housing,cap=cap,bat=bat)
print(json.dumps(report,indent=2))
