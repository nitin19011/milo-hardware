from pathlib import Path
import numpy as np,struct,json,collections
from rect_mesh import rect_mesh
exec(Path('work/build_cap_v5.py').read_text(encoding='utf-8-sig').split('# Replacement cap only')[0])
def read(p):
 b=Path(p).read_bytes();return np.array([struct.unpack_from('<12f',b,84+50*i)[3:] for i in range(struct.unpack_from('<I',b,80)[0])]).reshape(-1,3,3)
original=np.round(read(O/'Battery_flush_base.stl'),5)
# Eight stitch points, each with a pair of 2 mm holes. All behind cap overlap.
stations=[(x,y) for x in [4,24.2] for y in [11,18,25,32]]
holes=[(x,y+dy) for x,y in stations for dy in [-2,2]]
cuts=[(x-1,y-1,-1,x+1,y+1,2) for x,y in holes]
cuts +=[(x-.65,y-2,.8,x+.65,y+2,2) for x,y in stations]
samples=[-1.4,-1,-.75,-.5,-.25,0,.25,.5,.75,1,1.4]
xx=[0,1.2,27,28.2]+[x+v for x,y in holes for v in samples]
yy=[0,37.8,39]+[y+v for x,y in holes for v in samples]
def warp(t):
 p=t.copy()
 for x,y in holes:
  dx=p[:,:,0]-x;dy=p[:,:,1]-y;r=np.maximum(abs(dx),abs(dy));rr=np.hypot(dx,dy)
  mask=(r>=1-1e-7)&(r<1.4)&(rr>0)
  f=np.ones_like(r);f[mask]=1+(1.4-r[mask])/.4*(1/rr[mask]-1)
  p[:,:,0]=x+dx*f;p[:,:,1]=y+dy*f
 return p
floor_mesh=rect_mesh([(0,0,0,28.2,39,1.2)],cuts,(xx,yy,[]),warp)
# Preserve original sleeve walls, lips and detents; replace only the two floor surfaces.
def plane(t,axis,value):return np.all(np.isclose(t[:,:,axis],value,atol=1e-7,rtol=0),axis=1)
keep=~(plane(floor_mesh,0,0)|plane(floor_mesh,0,28.2)|plane(floor_mesh,1,0)|plane(floor_mesh,1,39))
cent=floor_mesh.mean(1)
top=plane(floor_mesh,2,1.2)
keep &= ~(top & ((cent[:,0]<1.2)|(cent[:,0]>27)|(cent[:,1]>37.8)))
patch=floor_mesh[keep]
old=original[~(plane(original,2,0)|plane(original,2,1.2))]
# Locate patch boundary vertices, then split neighbouring original triangle edges.
edges=collections.Counter()
for a in np.round(patch,7):
 for v,w in zip(a,np.roll(a,-1,axis=0)):edges[tuple(sorted((tuple(v),tuple(w))))]+=1
boundary=np.array(list({v for e,n in edges.items() if n==1 for v in e}))
stitched=[]
for a in old:
 ring=[]
 for u,v in zip(a,np.roll(a,-1,axis=0)):
  delta=v-u;den=delta@delta;f=(boundary-u)@delta/den
  dist=np.linalg.norm(boundary-(u+f[:,None]*delta),axis=1)
  selected=np.where((f>1e-7)&(f<1-1e-7)&(dist<2e-6))[0]
  ring.append(u)
  ring.extend(boundary[selected[np.argsort(f[selected])]])
 if len(ring)==3:stitched.append(a)
 else:
  c=a.mean(0)
  for u,v in zip(ring,ring[1:]+ring[:1]):stitched.append(np.array([c,u,v]))
base=np.concatenate([patch,np.array(stitched)])
cap=read(O/'Battery_flush_cap.stl')
assert np.allclose(base.min((0,1)),original.min((0,1)))
assert np.allclose(base.max((0,1)),original.max((0,1)))
report={'base':save(base,'Battery_flush_sewable_base.stl')}
report['combined']=save(np.concatenate([base,cap+[36.2,0,0]]),'Battery_flush_sewable_base_and_cap.stl')
report['stitch_points']=8;report['sewing_holes']=16;report['diameter_mm']=2;report['thread_recess_depth_mm']=.4
(O/'Battery_flush_sewable_checks.json').write_text(json.dumps(report,indent=2))
(O/'Battery_flush_sewable_notes.txt').write_text('''FLUSH BATTERY HOLDER WITH INTERNAL SEWING POINTS
Base retains the original 28.2 x 39 x 9.9 mm dimensions, battery cavity, side walls, lips and detents.
Only the floor was modified. Original wall geometry preserved to STL precision.
8 stitch points / 16 round holes, 2 mm diameter, arranged down both long edges inside base.
Each hole pair has a 0.4 mm-deep thread recess in the inner floor. Remaining floor below recess is 0.8 mm.
No external sewing tabs. No holes underneath the cap overlap.
Use thread that sits within the recess; avoid knots or loose loops protruding into the battery cavity.
Sew the empty base to the glove before inserting the battery. Check for rough hole edges first.
The original flush cap is unchanged: cap and base plastic undersides remain coplanar.
Combined STL contains one sewable base and one matching cap, separated by 8 mm and oriented for printing.
Print at 100% in millimetres. Physical fit and stitch durability still need checking.
''')
np.savez('work/battery_sewable_meshes.npz',base=base,cap=cap)
print(json.dumps(report,indent=2))
