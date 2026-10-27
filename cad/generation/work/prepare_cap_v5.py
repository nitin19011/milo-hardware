from pathlib import Path
p=Path('work/build_cap_v4.py').read_text(encoding='utf-8-sig')
p=p.replace("subs=[(.1*W,13.8,-1,.9*W,Y+1,wall+stop_depth+1),", "subs=[(.1*W,37.85,-1,.9*W,Y+1,wall+stop_depth+1),\n      (W/2-10,13.3,-1,W/2+10,33.3,wall+1),")
p=p.replace('assert L-2.3-41-13.8>=9','assert abs((L-2.3-41)-23.3)<1e-8\nassert 37.85-33.3>4.5')
p=p.replace('Mic_cap_v4_outer_skirt_RST_stops.stl','Mic_cap_v5_split_openings.stl').replace('cap_v4_mesh','cap_v5_mesh').replace('Mic_cap_v4','Mic_cap_v5').replace('REPLACEMENT CAP V4','REPLACEMENT CAP V5')
a=p.index('OPENING\n');b=p.index('ANTI-TILT STOPS\n',a)
p=p[:a]+'''OPENINGS
Two separate openings divided by a 4.55 mm-wide solid crossbar.
Upper opening: 35.88 mm wide (80% of housing width), reaching 26.45 mm from module top.
It retains clearance over the measured chip, plus top wire access.
Lower RST opening: 20 x 20 mm, centre 41 mm from module top.
RST opening is centred across housing width because button lateral position was not supplied.
Check lateral access before printing; the button may require an offset opening.

'''+p[b:]
Path('work/build_cap_v5.py').write_text(p,encoding='utf-8')
v=Path('work/preview_cap_v4.py').read_text(encoding='utf-8-sig')
v=v.replace('cap_v4_mesh','cap_v5_mesh').replace('Mic_cap_v4_preview','Mic_cap_v5_preview')
v=v.replace('Replacement cap: outer skirt, RST access and anti-tilt stops','Revised cap: separate cooling and reset openings')
v=v.replace('Fits your existing case. Two stops project inward by 11.6 mm.','Solid bridge between openings; outer skirt and 11.6 mm stops retained.')
v=v.replace('RST opening extends 9.5 mm beyond its centre. Print with the broad outer face down.','Reset opening: 20 x 20 mm, centred across width. Solid bridge: 4.55 mm wide.')
Path('work/preview_cap_v5.py').write_text(v,encoding='utf-8')
