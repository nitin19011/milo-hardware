from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
out=Path('outputs'); out.mkdir(exist_ok=True)
im=Image.new('RGB',(1600,1130),'#f3f6fa'); d=ImageDraw.Draw(im)
def font(n,b=False): return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),n)
navy='#183449'; muted='#576b7c'; blue='#287caf'; pale='#dceaf3'; teal='#137d7b'; orange='#d18637'
def text(x,y,s,n=22,c=navy,b=False): d.text((x,y),s,font=font(n,b),fill=c)
def line(points,c=muted,w=3): d.line(points,fill=c,width=w)
def dashed_box(box,c=muted):
 x,y,X,Y=box
 for a in range(x,X,15): line([(a,y),(min(a+8,X),y)],c,2); line([(a,Y),(min(a+8,X),Y)],c,2)
 for a in range(y,Y,15): line([(x,a),(x,min(a+8,Y))],c,2); line([(X,a),(X,min(a+8,Y))],c,2)
def arrow(x,y,X,Y,c=muted):
 import math
 line([(x,y),(X,Y)],c,2); a=math.atan2(Y-y,X-x)
 for angle in [a+.45,a-.45]: line([(X,Y),(X-12*math.cos(angle),Y-12*math.sin(angle))],c,2)
text(50,35,'Collar microphone enclosure â€” concept for review',36,b=True)
text(50,89,'40 Ã— 60 mm perfboard â€¢ microphone at the top â€¢ ESP connectors at the bottom',24,c=muted)
text(50,129,'Layout sketch only: enclosure depth, ESP overhang and opening positions still need measurements.',21,c=muted)
# front
text(75,205,'MIC FACE',26,b=True)
x,y,X,Y=105,275,455,835
d.rounded_rectangle((x,y,X,Y),radius=25,fill=pale,outline=blue,width=4)
dashed_box((133,305,427,665),'#8199a9')
text(162,613,'40 Ã— 60 board',20,c=muted)
# mic circle at top
d.ellipse((233,336,327,430),fill='#f3f6fa',outline=teal,width=4)
text(165,457,'Circular sound opening',21,c=teal,b=True)
text(155,488,'Aligned with the actual',19,c=muted)
text(166,513,'microphone inlet',19,c=muted)
line([(280,447),(280,430)],teal,2)
# bottom port indication
line([(155,835),(405,835)],orange,9)
text(100,865,'Bottom edge: USB + battery access',21,c=orange,b=True)
text(100,903,'Extra body length encloses the ESP',19,c=muted)
text(100,930,'section extending past the board.',19,c=muted)
# rear cap
text(600,205,'ESP FACE / REMOVABLE CAP',26,b=True)
x,y,X,Y=640,275,990,835
d.rounded_rectangle((x,y,X,Y),radius=25,fill='#b7d6e9',outline=blue,width=4)
# open top 80% notch
slotx,slotX=675,955
d.rectangle((slotx,270,slotX,365),fill='#f3f6fa')
line([(slotx,277),(slotx,365),(slotX,365),(slotX,277)],blue,4)
# dimension
line([(675,245),(955,245)],teal,2)
line([(675,238),(675,254)],teal,2); line([(955,238),(955,254)],teal,2)
text(719,251,'80% of cap width',18,c=teal)
text(703,389,'Open-edge wire slot',21,c=teal,b=True)
# ESP outline dotted
dashed_box((732,450,898,780),'#658299')
text(780,557,'ESP',24,c=muted,b=True)
text(745,593,'behind cap',18,c=muted)
# screw holes bottom+ mid sides
for cx,cy in [(658,407),(972,407),(658,810),(972,810)]:
 d.ellipse((cx-7,cy-7,cx+7,cy+7),fill='#f3f6fa',outline=blue,width=2)
text(618,865,'Screw-fastened cap; wire slot stays open',20,c=navy,b=True)
text(618,903,'Slot opens to the edge so connected',19,c=muted)
text(618,930,'wires can be laid in without threading.',19,c=muted)
# side cutaway
text(1130,205,'SIDE SECTION',26,b=True)
# shell U with no bottom? bottom wall ports show orange
line([(1185,320),(1185,835),(1445,835)],blue,8)
line([(1185,320),(1445,320)],blue,8)
line([(1445,400),(1445,835)],blue,8)
# board edge
line([(1280,346),(1280,680)],'#a57942',10)
# mic front at top
d.rectangle((1220,365,1274,416),fill='#66b4a0',outline=teal,width=2)
line([(1185,365),(1185,416)],'#f3f6fa',10)
# esp other side long
d.rectangle((1290,470,1380,780),fill='#9aaeba',outline=muted,width=2)
d.rectangle((1310,779,1360,800),fill=orange)
line([(1260,835),(1395,835)],orange,8)
text(1114,865,'Clearance on both board faces',20,b=True)
text(1125,903,'Board held by internal edge guides;',19,c=muted)
text(1125,930,'nothing presses against components.',19,c=muted)
text(1130,250,'Mic',20,c=teal); arrow(1160,280,1235,375,teal)
text(1355,250,'Cap',20,c=blue); arrow(1390,280,1445,435,blue)
text(1320,630,'ESP',20,c=navy)
line([(1245,680),(1405,680)],orange,2)
text(1300,709,'overhang',16,c=orange)
text(1190,990,'Depth and overhang: to be measured',19,c=muted)
line([(50,1030),(1550,1030)],'#ccd8e2',2)
text(50,1053,'Proposed construction: one tray + one removable cap. Final STL follows your layout feedback and measurements.',22,b=True)
im.save(out/'mic_enclosure_concept.png')

