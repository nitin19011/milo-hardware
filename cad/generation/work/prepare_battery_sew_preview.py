from pathlib import Path
p=Path('work/preview_battery_flush.py').read_text(encoding='utf-8-sig')
p=p.replace("m=np.load('work/battery_flush_meshes.npz');", "m=np.load('work/battery_flush_meshes.npz'); sew=np.load('work/battery_sewable_meshes.npz');")
p=p.replace("m['base'],(168,184,197)","sew['base'],(168,184,197)")
p=p.replace('Battery holder with a flush underside','Flush battery holder with internal sewing holes')
p=p.replace('Original battery space preserved; redesigned cap fits over the sides and top.','8 paired stitch points (16 holes), with recessed thread paths inside the base.')
p=p.replace('outputs/Battery_flush_preview.png','outputs/Battery_flush_sewable_preview.png')
Path('work/preview_battery_sewable.py').write_text(p,encoding='utf-8')
