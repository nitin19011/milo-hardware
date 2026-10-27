from pathlib import Path
p=Path('work/preview_necklace.py').read_text(encoding='utf-8-sig')
p=p.replace("m=np.load('work/necklace_enclosure_meshes.npz');", "t=np.load('work/cap_v4_mesh.npy');")
p=p[:p.index("txt(40,28,")]+'''
txt(40,28,'Replacement cap: outer skirt, RST access and anti-tilt stops',32)
txt(40,78,'Fits your existing case. Two stops project inward by 11.6 mm.',23)
render(t,(400,430),8,(55,153,205))
render(t,(1100,430),8,(112,167,193),True)
txt(120,725,'Inside face: two stops over perfboard edges',22)
txt(835,725,'5 mm skirt wraps around case exterior',22)
txt(40,790,'RST opening extends 9.5 mm beyond its centre. Print with the broad outer face down.',22)
im.save('outputs/Mic_cap_v4_preview.png')
'''
Path('work/preview_cap_v4.py').write_text(p,encoding='utf-8')
