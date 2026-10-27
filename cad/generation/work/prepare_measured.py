from pathlib import Path
p=Path('work/build_enclosures.py').read_text()
base=p.split('# Assumed:')[0]
Path('work/build_measured.py').write_text(base+r"""
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
(O/'Measured_v2_dimensions.txt').write_text('''MEASURED ENCLOSURE V2 â€” MILLIMETRES
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
""")

