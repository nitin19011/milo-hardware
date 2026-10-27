from pathlib import Path
import numpy as np, struct, json
from rect_mesh import rect_mesh
# Reuse established binary STL writer and manifold checks only.
lib=Path('work/build_cap_v5.py').read_text(encoding='utf-8-sig').split('# Replacement cap only')[0]
exec(lib)
W,L,H=56.2,64.6,18.8
mx,my,top=13.9,2.3,62.3
floor,wall,slip=1.8,1.8,.15
board_z=floor+.5+13.5
support_z=board_z-1.6 # assumed perfboard thickness 1.6
stop_depth=H-board_z-.2
assert abs(stop_depth-2.8)<1e-6
# Main tray + side pocket. IMU is 16 x 20, projecting 11.6 left of perfboard.
outer=[(11.6,0,0,W,L,H),(0,24.7,0,19.3,49.3,H)]
cavities=[(13.4,1.8,floor,54.4,62.8,H+1),(1.8,26.5,floor,19.3,47.5,H+1)]
wirecuts=[(mx-.3,62.7,2.8,mx+13.5,L+2,H+1),
          (11.4,49.4,2.8,13.5,60.8,H+1),
          (mx+12,-2,floor,mx+39,2,H+1)]
# Broad supports on four narrow board edge areas, with opposing cap stops.
pads=[(mx+.4,my+4,mx+2.4,my+7),(mx+37.6,my+4,mx+39.6,my+7),
      (mx+.4,top-8,mx+2.4,top-5),(mx+37.6,top-8,mx+39.6,top-5)]
supports=[(x,y,floor,X,Y,support_z) for x,y,X,Y in pads]
# 12 paired sewing stations: 4 right, 4 left/IMU, 2 top, 2 bottom.
stations=[(mx+36,my+v,'v') for v in [10,23,36,49]]
stations += [(mx+4,my+10,'v'),(mx+4,my+19,'v'),(5.7,31.8,'v'),(5.7,41.8,'v')]
stations += [(mx+22,top-3.5,'h'),(mx+33,top-3.5,'h'),(mx+8,my+3.5,'h'),(mx+21,my+3.5,'h')]
holes=[];recess=[]
for x,y,ori in stations:
 dx,dy=(2.5,0) if ori=='h' else (0,2.5)
 holes.extend([(x-dx,y-dy),(x+dx,y+dy)])
 recess.append((x-dx-.8,y-dy-.8,floor-.35,x+dx+.8,y+dy+.8,floor+.1))
subholes=[(x-1.25,y-1.25,-1,x+1.25,y+1.25,floor+.1) for x,y in holes]
# Round external XY corners with a small radius, while retaining wall clearance.
basecorners=[(11.6,0,1,1),(W,0,-1,1),(W,L,-1,-1),(11.6,L,1,-1),(0,24.7,1,1),(0,49.3,1,-1)]
def round_corners(t,corners,r=1.0):
 p=t.copy()
 for x,y,sx,sy in corners:
  cx=x+sx*r;cy=y+sy*r
  dx=p[:,:,0]-cx;dy=p[:,:,1]-cy
  mask=(dx*sx<=1e-7)&(dy*sy<=1e-7)&(dx*sx>=-r-1e-7)&(dy*sy>=-r-1e-7)
  rr=np.hypot(dx,dy);ri=np.maximum(abs(dx),abs(dy));f=np.ones_like(rr)
  np.divide(ri,rr,out=f,where=mask&(rr>1e-10))
  p[:,:,0]=cx+dx*f;p[:,:,1]=cy+dy*f
 return p

def basewarp(t):
 p=round_corners(t,basecorners)
 for x,y in holes:
  dx=p[:,:,0]-x;dy=p[:,:,1]-y;r=np.maximum(abs(dx),abs(dy));rr=np.hypot(dx,dy)
  mask=(r>=1.25-1e-6)&(r<1.75)&(rr>0)
  f=np.ones_like(r);f[mask]=1+(1.75-r[mask])/.5*(1.25/rr[mask]-1)
  p[:,:,0]=x+dx*f;p[:,:,1]=y+dy*f
 return p
samples=[-1.75,-1.25,-.9375,-.625,-.3125,0,.3125,.625,.9375,1.25,1.75]
xx=[x+v for x,y in holes for v in samples];yy=[y+v for x,y in holes for v in samples]
for x,y,sx,sy in basecorners:
 xx.extend([x+sx*v for v in np.linspace(0,1,6)]);yy.extend([y+sy*v for v in np.linspace(0,1,6)])
base=rect_mesh(outer,cavities+wirecuts+subholes+recess,(xx,yy,[]),basewarp,keep=supports)
# Outside-fitting cap: same plan, expanded 0.15 mm clearance + 1.6 mm skirt.
e=.15+1.6
capouter=[(11.6-e,-e,0,W+e,L+e,6.6),(-e,24.7-e,0,19.3+e,49.3+e,6.6)]
capcavity=[(11.6-.15,-.15,1.6,W+.15,L+.15,7),(-.15,24.7-.15,1.6,19.3+.15,49.3+.15,7)]
# Coordinates inferred from annotated photo: chip nearest side at ~17 mm;
# RST x=28 mm; exact longitudinal placement uses user annotations.
chip_x=mx+17;chip_top=top-9.9
rst_x=mx+28;rst_y=top-42.2
imu_x=mx-11.6+8;imu_y=top-15.3-10
opencuts=[(chip_x-1,chip_top-19,-1,chip_x+17,chip_top+1,8),
          (rst_x-10,rst_y-10,-1,rst_x+10,rst_y+10,8),
          (imu_x-4,imu_y-4,-1,imu_x+4,imu_y+4,8)]
capwire=[(mx-.3,62.7,-1,mx+13.5,L+e+1,8),
         (11.6-e-1,49.4,-1,13.5,60.8,8),
         (mx+12,-e-1,1.6,mx+39,2,8)]
stops=[(x,y,1.6,X,Y,1.6+stop_depth) for x,y,X,Y in pads]
capcorners=[(11.6-e,-e,1,1),(W+e,-e,-1,1),(W+e,L+e,-1,-1),(11.6-e,L+e,1,-1),(-e,24.7-e,1,1),(-e,49.3+e,1,-1)]
xx=[];yy=[]
for x,y,sx,sy in capcorners:
 xx.extend([x+sx*v for v in np.linspace(0,1,6)]);yy.extend([y+sy*v for v in np.linspace(0,1,6)])
cap_assembly=rect_mesh(capouter,capcavity+opencuts+capwire,(xx,yy,[]),lambda t:round_corners(t,capcorners),keep=stops)
# Mirror X in print view so flipping the cap over aligns its asymmetric IMU pocket.
cap=cap_assembly.copy();cap[:,:,0]*=-1;cap=cap[:,[0,2,1]];cap-=cap.min((0,1))
# Verify all stop/support footprints match and don't meet the three apertures.
for x,y,X,Y in pads:
 for a,b,z,A,B,Z in opencuts:assert X<=a or x>=A or Y<=b or y>=B
assert abs((H-stop_depth)-board_z-.2)<1e-6
assert chip_top-19>rst_y+10 # solid middle bridge
# Stitch holes miss support contact footprints.
for x,y in holes:
 for a,b,A,B in pads:assert x+1.25<=a or x-1.25>=A or y+1.25<=b or y-1.25>=B
info={}
info['base']=save(base,'Glove_housing_base_v1.stl')
info['cap']=save(cap,'Glove_housing_cap_v1.stl')
placed_cap=cap+[W+8,0,0]
info['combined']=save(np.concatenate([base,placed_cap]),'Glove_housing_base_and_cap_v1.stl')
np.savez('work/glove_final_meshes.npz',base=base,cap=cap,cap_assembly=cap_assembly)
(O/'Glove_housing_v1_checks.json').write_text(json.dumps(info,indent=2))
(O/'Glove_housing_v1_print_notes.txt').write_text(f'''GLOVE HOUSING V1 - MILLIMETRES
Measured perfboard: 40 x 60. Total assembly thickness: 16.
IMU: 16 x 20, extends 11.6 beyond left perfboard edge.
IMU nearest top edge: 15.3 from perfboard top.
Bare perfboard upper face: 13.5 above the assembly lowest point.
Perfboard thickness assumed 1.6; support heights depend on this.

DIMENSIONS
Base overall: 56.2 x 64.6 x 18.8, including the local IMU pocket.
Base main rectangle: 44.6 wide; 11.6 extra width only at IMU pocket.
Internal vertical space: 17, giving 1 mm total allowance around 16 mm assembly.
Nominal assembled maximum envelope including external cap: 59.7 x 68.1 x 20.4.
Base floor: 1.8; side walls: 1.8; cap face/skirt wall: 1.6.
Cap outer overlap: 5; lateral fit clearance: 0.15 per side.
Four board-edge supports reach Z={support_z:.2f} from base underside.
Four matching cap stops extend {stop_depth:.2f} from cap underside, leaving 0.2 above the seated board.
Confirm contact areas are clear of wires/solder/components. Avoid forcing the fit.

OPENINGS
Separate ESP cooling opening: 18 x 20, based on 16 x 18 chip annotation.
Separate RST opening: 20 x 20, centre 42.2 from top.
IMU opening: 8 x 8, centred on IMU board.
ESP side position (17 mm to chip edge; 28 mm to RST centre) is estimated from photo;
these lateral dimensions were not supplied explicitly. Verify alignment in a slicer before printing.
Top wire exit: 13.8 wide. Upper-left exit: 11.4 long. Bottom USB/battery exit: 27 wide.

SEWING
12 paired stitch points / 24 round 2.5 mm holes, all within the base perimeter.
Recessed thread paths: 0.35 deep. No projecting sewing tabs.
Sew empty base onto glove before installing electronics. Keep knots below board clearance.

PRINTING
Combined STL contains two separated parts on the bed (8 mm gap).
Print at 100% in millimetres. Base floor and broad outer cap face already face down.
The cap is intentionally mirrored in print view: flip it over to align the asymmetric IMU pocket.
Review thin features, holes and skirt clearances in slicer before printing.
This is a removable friction cap, not a snap latch. Grip remains printer-dependent.
Mesh validation: closed edges, consistent winding, nonzero faces, positive volume.
Physical fit and wear strength are not tested.
''')
print(json.dumps(info,indent=2))

