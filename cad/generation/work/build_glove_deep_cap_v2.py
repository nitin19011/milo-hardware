"""Replacement outside-fitting glove cap; existing printed base is unchanged."""
from pathlib import Path
import json,hashlib
import numpy as np

# Reuse the original measured coordinates, corner treatment and validated STL writer.
# Stop before the original base meshing/export so no v1 output is overwritten.
original=Path('work/build_glove_final.py').read_text(encoding='utf-8')
exec(original[:original.index('base=rect_mesh(')])
old=np.load('work/glove_final_meshes.npz')
old_base_hash=hashlib.sha256(Path('outputs/Glove_housing_base_v1.stl').read_bytes()).hexdigest()

overlap=14.0
face=1.6
height=face+overlap
clearance=.15
e=clearance+1.6
cut_top=height+1
capouter=[(11.6-e,-e,0,W+e,L+e,height),(-e,24.7-e,0,19.3+e,49.3+e,height)]
capcavity=[(11.6-clearance,-clearance,face,W+clearance,L+clearance,height+.4),
           (-clearance,24.7-clearance,face,19.3+clearance,49.3+clearance,height+.4)]
chip_x=mx+17;chip_top=top-9.9
rst_x=mx+28;rst_y=top-42.2
imu_x=mx-11.6+8;imu_y=top-15.3-10
opencuts=[(chip_x-1,chip_top-19,-1,chip_x+17,chip_top+1,cut_top),
          (rst_x-10,rst_y-10,-1,rst_x+10,rst_y+10,cut_top),
          (imu_x-4,imu_y-4,-1,imu_x+4,imu_y+4,cut_top)]
# Extend every original wire/port notch to the new skirt edge, so deeper walls
# cannot cover a cable route or prevent fitting the already-sewn base.
capwire=[(mx-.3,62.7,-1,mx+13.5,L+e+1,cut_top),
         (11.6-e-1,49.4,-1,13.5,60.8,cut_top),
         (mx+12,-e-1,face,mx+39,2,cut_top)]
stops=[(x,y,face,X,Y,face+stop_depth) for x,y,X,Y in pads]
capcorners=[(11.6-e,-e,1,1),(W+e,-e,-1,1),(W+e,L+e,-1,-1),
            (11.6-e,L+e,1,-1),(-e,24.7-e,1,1),(-e,49.3+e,1,-1)]
xx=[];yy=[]
for x,y,sx,sy in capcorners:
    xx.extend([x+sx*v for v in np.linspace(0,1,6)])
    yy.extend([y+sy*v for v in np.linspace(0,1,6)])
cap_assembly=rect_mesh(capouter,capcavity+opencuts+capwire,(xx,yy,[]),lambda t:round_corners(t,capcorners),keep=stops)
cap=cap_assembly.copy();cap[:,:,0]*=-1;cap=cap[:,[0,2,1]];cap-=cap.min((0,1))
checks=save(cap,'Glove_housing_cap_v2_deep_skirt.stl')

# Compare horizontal cross-sections against v1, and count connected solids.
# For a closed surface, plane intersections and their lengths fully describe each slice.
def slice_signature(mesh,z):
    lines=[]
    for tri in mesh:
        points=[]
        for a,b in zip(tri,np.roll(tri,-1,axis=0)):
            if (a[2]<z<b[2]) or (b[2]<z<a[2]):points.append(a[:2]+(b[:2]-a[:2])*(z-a[2])/(b[2]-a[2]))
        if len(points)==2:
            p,q=sorted(tuple(v) for v in points)
            lines.append((p,q))
    return sorted(lines)

for z in [.8,2.2,4.9,6.1]:
    # Different skirt heights subdivide the same contour segments at different
    # points. Check symmetric point-to-segment distance and total perimeter.
    previous=np.array(slice_signature(old['cap_assembly'],z));revised=np.array(slice_signature(cap_assembly,z))
    def distances(a,b):
        points=np.concatenate([a[:,0],a[:,1],a.mean(axis=1)])
        origin=b[:,0];delta=b[:,1]-origin
        offset=points[:,None,:]-origin[None,:,:]
        alpha=np.clip(np.einsum('nmi,mi->nm',offset,delta)/np.einsum('mi,mi->m',delta,delta),0,1)
        return np.linalg.norm(offset-alpha[:,:,None]*delta[None,:,:],axis=2).min(axis=1).max()
    assert max(distances(previous,revised),distances(revised,previous))<1e-5,z
    assert abs(np.linalg.norm(previous[:,1]-previous[:,0],axis=1).sum()-np.linalg.norm(revised[:,1]-revised[:,0],axis=1).sum())<1e-5,z

vertices,inverse=np.unique(np.round(cap.reshape(-1,3),6),axis=0,return_inverse=True)
parent=np.arange(len(vertices))
def find(x):
    while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
    return x
for tri in inverse.reshape(-1,3):
    for a,b in [(tri[0],tri[1]),(tri[1],tri[2])]:parent[find(a)]=find(b)
assert len({find(i) for i in range(len(vertices))})==1
assert H-overlap>floor
assert hashlib.sha256(Path('outputs/Glove_housing_base_v1.stl').read_bytes()).hexdigest()==old_base_hash
checks.update(old_overlap_mm=5,new_overlap_mm=overlap,overlap_ratio=overlap/5,
              base_clearance_below_skirt_mm=round(H-overlap,3),side_clearance_mm=clearance,
              skirt_wall_mm=1.6,face_thickness_mm=face,stop_depth_mm=round(stop_depth,3),
              one_connected_solid=True,existing_height_cross_sections_match_v1=True,
              original_base_file_unchanged=True,wire_cuts_extended_through_new_skirt=True,
              retention='removable friction fit; no snap latch; physical fit/retention untested')
Path('outputs/Glove_housing_cap_v2_checks.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8')
np.savez('work/glove_deep_cap_v2_meshes.npz',cap=cap,cap_assembly=cap_assembly,old_cap=old['cap'])
Path('outputs/Glove_housing_cap_v2_print_notes.txt').write_text('''GLOVE CAP V2 - DEEP OUTER SKIRT - MILLIMETRES

Replacement cap ONLY, for your already-printed Glove_housing_base_v1.
No new base is needed. The original base STL was not changed.

WHAT CHANGED
Outside overlap is now 14 mm (previously 5 mm): 2.8 times the engagement depth.
Skirt covers about 74% of the base height along closed wall sections.
When seated, the skirt stops 4.8 mm above the base underside, leaving clearance
for the sewn base and glove rather than reaching underneath them.
Cap printed height is 15.6 mm including its 1.6 mm face (previously 6.6 mm).
Cap XY envelope is unchanged: 59.7 x 68.1 mm, including the IMU pocket.
Assembled overall enclosure height remains 20.4 mm; the extra skirt extends down.

FIT AND OPENINGS
Same outside-fitting geometry, 0.15 mm clearance per side and 1.6 mm skirt walls.
Same 2.8 mm internal anti-tilt stops and original component clearance.
ESP cooling opening, 20 x 20 mm reset access and 8 x 8 mm IMU opening retained.
All top/side wire exits and the bottom USB/battery opening continue through the
full skirt depth. Sewing points remain in the existing base.

PRINT
Print only Glove_housing_cap_v2_deep_skirt.stl at 100%, in millimetres.
Broad outside face is already on the bed; the deeper skirt points upward.
Flip the cap over after printing to align the asymmetric IMU pocket with the base.
Keep the print orientation and fit settings that worked for your first cap.
Check the fit gently on the sewn case before vigorous movement.
This has longer friction engagement, not a positive latch. Actual grip and impact
retention depend on the print/material and have not been physically tested.
''',encoding='utf-8')
print(json.dumps(checks,indent=2))
