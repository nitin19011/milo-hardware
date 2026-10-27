from pathlib import Path
p=Path('work/build_necklace.py').read_text(encoding='utf-8-sig')
base=p.split('# Measured module')[0]
code='''
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
Path('work/outer_cap_plan.txt').write_text(str(info)+'\\n5 mm external overlap; opening and stopper geometry pending actual reset/PCB measurements.')
print(info)
'''
Path('work/build_outer_cap_draft.py').write_text(base+code,encoding='utf-8')
