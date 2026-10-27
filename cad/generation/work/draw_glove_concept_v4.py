from PIL import Image,ImageDraw,ImageFont
im=Image.new('RGB',(1800,1280),'#f3f6fa');d=ImageDraw.Draw(im)
C={'ink':'#19364b','muted':'#526c7c','body':'#d3e4ef','edge':'#337da4','board':'#a9c8b3','imu':'#71a9c7','teal':'#137f79','orange':'#b26b22','white':'#f3f6fa'}
def txt(x,y,s,n=21,c='ink',bold=False):
 d.text((x,y),s,font=ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),n),fill=C.get(c,c))
def line(p,c='muted',w=2):d.line(p,fill=C.get(c,c),width=w)
def leader(p):
 line(p);x,y=p[-1];d.ellipse((x-3,y-3,x+3,y+3),fill=C['muted'])
def rr(box,fill,outline='edge',r=12,w=3):d.rounded_rectangle(box,r,fill=C.get(fill,fill),outline=C.get(outline,outline),width=w)
def dashed(box,c='muted'):
 x,y,X,Y=box
 for u in range(int(x),int(X),14):line([(u,y),(min(u+7,X),y)],c);line([(u,Y),(min(u+7,X),Y)],c)
 for v in range(int(y),int(Y),14):line([(x,v),(x,min(v+7,Y))],c);line([(X,v),(X,min(v+7,Y))],c)
txt(45,30,'Glove ESP housing â€” labelled design for review',37,bold=True)
txt(45,87,'Top reference and component layout follow your photo. This is a concept, not the final STL.',23,c='muted')
txt(255,167,'BASE: internal sewing layout',26,bold=True)
txt(1045,167,'CAP: fitted over the base',26,bold=True)
# Main tray and stepped side pocket: larger left footprint only beside the IMU.
def outline(ox,fill):
 rr((248+ox,288,552+ox,732),fill)
 rr((148+ox,397,268+ox,562),fill)
 # remove interior joining seam
 d.rectangle((249+ox,400,269+ox,559),fill=C[fill])
for ox in [0,790]:
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
# top and left open-edge wire notches (not enclosed threading holes)
d.rectangle((278,283,354,301),fill=C['white'])
d.rectangle((244,333,261,390),fill=C['white'])
for x,c in [(293,'#c94040'),(311,'#233542'),(333,'#c94040')]:line([(x,318),(x,249),(x-15,229)],c,5)
for yy,c in [(350,'#c94040'),(369,'#233542')]:line([(294,yy),(180,yy),(156,yy-7)],c,5)
# labelled dimensions
line([(260,269),(540,269)],'muted');line([(260,262),(260,276)]);line([(540,262),(540,276)])
txt(377,237,'40 mm',20,c='muted')
line([(633,300),(633,720)]);line([(626,300),(640,300)]);line([(626,720),(640,720)])
txt(644,500,'60 mm',21,c='muted')
# base leaders


txt(38,199,'Wire exits',22,c='teal',bold=True)
txt(38,229,'Top + upper-left',20,c='muted')
leader([(160,251),(212,251),(248,360)])
txt(35,579,'IMU side pocket',22,bold=True)
txt(35,610,'Protects protruding board',19,c='muted')
leader([(170,573),(181,550)])
txt(40,770,'12 internal stitch points',22,c='teal',bold=True)
txt(40,803,'24 holes in recessed floor strips',19,c='muted')
txt(40,830,'Sew first, then install the module',19,c='muted')
leader([(215,764),(270,749),(292,706)])
txt(369,808,'USB + battery access',21,c='orange',bold=True)
leader([(480,797),(480,770),(473,732)])
# Cap upper cooling and separate reset hole.
rr((1158,359,1298,499),'white',outline='teal',r=8)
rr((1175,525.4,1315,665.4),'white',outline='teal',r=8)
# Proposed 8 x 8 mm IMU chip opening, centred on 16 x 20 mm module footprint.
rr((984,449,1040,505),'white',outline='teal',r=6)
txt(733,427,'IMU chip opening',21,c='teal',bold=True)
txt(733,457,'Centred over main chip',18,c='muted')
txt(733,483,'Proposed 8 Ã— 8 mm',18,c='muted')
leader([(930,512),(967,512),(984,477)])
# cap top and upper-left relieved to leave base notches open
d.rectangle((1068,283,1144,321),fill=C['white'])
line([(1068,290),(1068,321),(1144,321),(1144,290)],'edge',3)
d.rectangle((1032,333,1057,390),fill=C['white'])
line([(1038,333),(1057,333),(1057,390),(1038,390)],'edge',3)
# leave lower end ports open in cap skirt
line([(1155,732),(1290,732)],'orange',8)
# label top direction and cap feature notes
txt(1440,288,'Cooling opening',23,c='teal',bold=True)
txt(1440,324,'Over the main ESP chip',20,c='muted')
leader([(1430,341),(1372,341),(1298,403)])
txt(1440,447,'Solid middle bridge',23,bold=True)
leader([(1430,480),(1368,480),(1298,512)])
txt(1440,565,'RST finger opening',23,c='teal',bold=True)
txt(1440,601,'Proposed 20 Ã— 20 mm',20,c='muted')
txt(1440,631,'Centre: 42.2 mm from top',20,c='muted')
leader([(1430,617),(1372,617),(1315,595)])
txt(1024,808,'Removable outer-fitting cap',22,bold=True)
txt(1024,842,'Skirt relieved at every wire and connector exit',19,c='muted')
# Section lower panel
line([(40,900),(1760,900)],'#cbd9e2')
txt(45,929,'SIDE SECTION â€” mounting on the glove',25,bold=True)
# glove textile band
rr((88,1128,838,1168),'#d4d8e2',outline='#909eb0',r=12,w=2)
# housing floor and walls
rr((211,1096,698,1126),'body',r=7)
d.rectangle((211,1009,225,1110),fill=C['body'],outline=C['edge'],width=2)
d.rectangle((684,1009,698,1110),fill=C['body'],outline=C['edge'],width=2)
# board + representative components
line([(239,1060),(670,1060)],'#628966',7)
d.rectangle((340,1025,525,1055),fill='#68817c')
# support feet at unused edges
d.rectangle((233,1064,256,1095),fill='#83a5b9')
d.rectangle((648,1064,671,1095),fill='#83a5b9')
# Thread passes through recessed holes in the floor, below board supports.
for x in [282,589]:
 d.rectangle((x-3,1096,x+29,1103),fill=C['white'])
 line([(x,1100),(x,1153),(x+26,1153),(x+26,1100),(x,1100)],'teal',3)
txt(289,1176,'Glove fabric',20,c='muted')
txt(88,975,'Recessed stitches inside floor',20,c='teal')
leader([(153,1018),(189,1080),(286,1100)])
txt(887,940,'Design choices',23,bold=True)
txt(887,983,'â€¢ Smooth outer perimeter: no projecting sewing tabs',21)
txt(887,1018,'â€¢ Twelve paired stitch points (24 proposed Ã˜2.5 mm holes)',21)
txt(887,1053,'â€¢ Recessed thread paths sit below the supported electronics',21)
txt(887,1088,'â€¢ Cap stops over bare board edges limit upward tilting',21)
txt(887,1141,'Confirmed: total module thickness = 16 mm',22,c='teal',bold=True)
txt(887,1176,'Pending: IMU overhang and board-edge height for the stops.',21,c='muted')
txt(45,1230,'Concept only â€” 40 Ã— 60 mm perfboard; 16 mm module thickness. Overall width and support heights remain to be set.',21,c='muted')
# Side-section cap and proposed underside stops.
rr((205,1000,705,1012),'#a2c8df',r=4,w=2)
d.rectangle((239,1012,254,1056),fill=C['orange'])
d.rectangle((648,1012,663,1056),fill=C['orange'])
txt(445,967,'Cap + anti-tilt stops',20,c='orange',bold=True)
leader([(563,994),(655,994),(655,1034)])
im.save('outputs/Glove_ESP_IMU_vent_concept_v4.png')



