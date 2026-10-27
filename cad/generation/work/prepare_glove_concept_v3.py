from pathlib import Path
p=Path('work/draw_glove_concept_v2.py').read_text(encoding='utf-8-sig')
a=p.index('for ox in [0,790]:');b=p.index('# top and left open-edge wire notches',a)
p=p[:a]+'''for ox in [0,790]:
 outline(ox,'body')
# Empty base floor view, with module outline dashed.
dashed((260,300,540,720),'muted')
dashed((166,407,278,547),'muted')
txt(315,473,'Perfboard footprint',20,c='muted')
txt(329,506,'40 Ã— 60 mm',22,c='muted')
txt(310,552,'Electronics removed',19,c='muted')
txt(331,580,'to show stitches',19,c='muted')
# Twelve paired stitch stations (24 holes), all inside the existing perimeter.
stations=[(175,441,'v'),(175,512,'v'),(276,615,'v'),(276,680,'v'),
          (524,345,'v'),(524,450,'v'),(524,555,'v'),(524,660,'v'),
          (400,313,'h'),(475,313,'h'),(292,706,'h'),(338,706,'h')]
for x,y,orient in stations:
 dx,dy=(9,0) if orient=='h' else (0,9)
 rr((x-dx-7,y-dy-7,x+dx+7,y+dy+7),'#b6d8d2',outline='teal',r=5,w=1)
 for s in [-1,1]:
  xx,yy=x+s*dx,y+s*dy
  d.ellipse((xx-4,yy-4,xx+4,yy+4),fill=C['white'],outline=C['teal'],width=2)
 line([(x-dx,y-dy),(x+dx,y+dy)],'teal',2)
# Connector clearance shown schematically.
line([(365,732),(500,732)],'orange',8)
''' +p[b:]
p=p.replace('BASE: electronics seated inside','BASE: internal sewing layout')
p=p.replace('Four sewing tabs','12 internal stitch points').replace('Two holes per tab; accessible','24 holes in recessed floor strips').replace('with the lid fitted','Sew first, then install the module')
p=p.replace('leader([(215,764),(215,722),(211,709)])','leader([(215,764),(270,749),(292,706)])')
p=p.replace('leader([(480,797),(480,770),(473,741)])','leader([(480,797),(480,770),(473,732)])')
a=p.index('# stitch flange and cord cross section');b=p.index("txt(289,1176",a)
p=p[:a]+'''# Thread passes through recessed holes in the floor, below board supports.
for x in [282,589]:
 d.rectangle((x-3,1096,x+29,1103),fill=C['white'])
 line([(x,1100),(x,1153),(x+26,1153),(x+26,1100),(x,1100)],'teal',3)
''' +p[b:]
p=p.replace('Thread through external tabs','Recessed stitches inside floor').replace('leader([(153,1018),(181,1050),(181,1118)])','leader([(153,1018),(189,1080),(286,1100)])')
p=p.replace('â€¢ Rounded base and tabs against the glove','â€¢ Smooth outer perimeter: no projecting sewing tabs')
p=p.replace('â€¢ Eight proposed Ã˜2.5 mm sewing holes, outside the electronics','â€¢ Twelve paired stitch points (24 proposed Ã˜2.5 mm holes)')
p=p.replace('â€¢ Board supports keep underside solder joints off the floor','â€¢ Recessed thread paths sit below the supported electronics')
p=p.replace('Glove_ESP_housing_labelled_concept_v2.png','Glove_ESP_internal_sewing_concept_v3.png')
Path('work/draw_glove_concept_v3.py').write_text(p,encoding='utf-8')
