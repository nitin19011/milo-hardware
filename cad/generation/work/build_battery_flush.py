from pathlib import Path
import numpy as np,struct,json,shutil
exec(Path('work/build_cap_v5.py').read_text(encoding='utf-8-sig').split('# Replacement cap only')[0])
source=Path('inputs/LiPo_600mAh_slide_sleeve.stl')
b=source.read_bytes();n=struct.unpack_from('<I',b,80)[0]
base=np.array([struct.unpack_from('<12f',b,84+50*i)[3:] for i in range(n)]).reshape(-1,3,3)
# Three-sided outer saddle: no skirt under the flat Z=0 mounting face.
c=.2;t=1.6
cap=mesh([(-c-t,-t,0,28.2+c+t,8,9.9+c+t)],
         [(-c,0,-1,28.2+c,9,9.9+c),
          (1.2,-t-1,4.95,7.2,9,13),
          (21,-t-1,4.95,27,9,13)])
assert abs(base[:,:,2].min())<1e-7 and abs(cap[:,:,2].min())<1e-7
# Check cap overlapping length lies entirely outside the original sleeve envelope.
# Inside gap is 0.2 mm on sides/top; end plate occupies only Y<0.
assert -c<base[:,:,0].min() and 28.2+c>base[:,:,0].max()
assert 9.9+c>base[:,:,2].max()
base_info=validate(base)
cap_assembly_info=validate(cap)
# Preserve the user's base byte-for-byte: cavity and internal detents unchanged.
shutil.copyfile(source,O/'Battery_flush_base.stl')
cap_print=cap[:,:,[0,2,1]].copy();cap_print[:,:,1]*=-1;cap_print-=cap_print.min((0,1))
cap_info=save(cap_print,'Battery_flush_cap.stl')
combined=np.concatenate([base,cap_print+[36.2,0,0]])
combined_info=save(combined,'Battery_flush_base_and_cap.stl')
np.savez('work/battery_flush_meshes.npz',base=base,cap=cap,cap_print=cap_print)
report={'base':base_info,'cap':cap_info,'combined':combined_info,'coplanar_mounting_face_z_mm':0,'base_identical_to_original':(O/'Battery_flush_base.stl').read_bytes()==source.read_bytes()}
(O/'Battery_flush_checks.json').write_text(json.dumps(report,indent=2))
(O/'Battery_flush_print_notes.txt').write_text('''BATTERY HOLDER - FLUSH UNDERSIDE
One continuous mounting plane: both base underside and cap underside are at Z=0 when assembled.
The cap wraps around the two sides and top, with no plastic skirt beneath the base.
The cap front face extends down to the same mounting plane as the base.

Base is a byte-for-byte copy of the original LiPo_600mAh_slide_sleeve.stl.
Original dimensions 28.2 x 39 x 9.9 mm, original battery cavity and retaining details unchanged.
Compatible with the same battery as the original housing; no cap feature projects into battery space.
Cap overlap: 8 mm. Cap walls/end plate: 1.6 mm. Side/top clearance: 0.2 mm per side.
Assembled maximum dimensions: 31.8 wide x 40.6 long x 11.7 high.
Only underside is flush; cap still projects beyond the sides/top.
Two 6 mm-wide wire notches near opposite ends retain the preceding wire routing.

Combined file: one base + one cap, with 8 mm spacing, already placed on print bed.
Cap is printed on its end face; rotate into position when assembling.
Print at 100% in millimetres. Physical fit and retention remain printer-dependent.
This three-sided cap is a slip fit, not a locking latch. Secure with a tape tab across top/side if needed,
keeping the underside clear if it is used as the mounting surface.
''')
print(json.dumps(report,indent=2))
