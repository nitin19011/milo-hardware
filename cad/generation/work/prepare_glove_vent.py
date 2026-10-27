from pathlib import Path
p=Path('work/draw_glove_concept_v3.py').read_text(encoding='utf-8-sig')
p=p.replace("# cap top and upper-left relieved to leave base notches open", """# Proposed 8 x 8 mm IMU chip opening, centred on 16 x 20 mm module footprint.
rr((984,449,1040,505),'white',outline='teal',r=6)
txt(733,427,'IMU chip opening',21,c='teal',bold=True)
txt(733,457,'Centred; proposed 8 Ã— 8 mm',18,c='muted')
leader([(930,490),(964,490),(984,477)])
# cap top and upper-left relieved to leave base notches open""")
p=p.replace('Glove_ESP_internal_sewing_concept_v3.png','Glove_ESP_IMU_vent_concept_v4.png')
Path('work/draw_glove_concept_v4.py').write_text(p,encoding='utf-8')
