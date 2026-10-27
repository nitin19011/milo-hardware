from pathlib import Path
p=Path('work/build_outer_cap_reset_draft.py').read_text(encoding='utf-8-sig')
p=p.split('# Preliminary outer cap')[0]+'''
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
'''
Path('work/build_cap_v4.py').write_text(p,encoding='utf-8')
