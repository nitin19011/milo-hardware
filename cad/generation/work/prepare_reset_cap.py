from pathlib import Path
s=Path('work/build_outer_cap_draft.py').read_text(encoding='utf-8-sig')
s=s.replace('37.85','13.8')
s=s.replace("np.save('work/outer_cap_pending_reset_and_stops.npy',cap)","np.save('work/outer_cap_reset_opening_pending_stops.npy',cap)")
s=s.replace("Path('work/outer_cap_plan.txt')","Path('work/outer_cap_reset_plan.txt')")
s=s.replace('opening and stopper geometry pending actual reset/PCB measurements.','RST centre: 41 mm from module top = case Y23.3; opening reaches Y13.8, giving 9.5 mm past centre. Opening width35.88 mm. Anti-tilt stop depth pending rim-to-perfboard measurement.')
Path('work/build_outer_cap_reset_draft.py').write_text(s,encoding='utf-8')
