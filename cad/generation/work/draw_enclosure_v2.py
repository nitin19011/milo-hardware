from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
im=Image.new('RGB',(1600,1080),'#f3f6fa'); d=ImageDraw.Draw(im)
navy='#183449'; muted='#576b7c'; blue='#287caf'; pale='#dceaf3'; teal='#137d7b'; orange='#c17a28'
def text(x,y,s,n=22,c=navy,b=False): d.text((x,y),s,font=ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),n),fill=c)
def line(p,c=muted,w=3): d.line(p,fill=c,width=w)
def dash(box,c=muted):
 x,y,X,Y=box
 for a in range(x,X,15): line([(a,y),(min(a+8,X),y)],c,2); line([(a,Y),(min(a+8,X),Y)],c,2)
 for a in range(y,Y,15): line([(x,a),(x,min(a+8,Y))],c,2); line([(X,a),(X,min(a+8,Y))],c,2)
text(45,30,'Compact collar enclosure â€” revised concept',36,b=True)
text(45,85,'Small ESP overhang at the TOP â€¢ close fit around the 40 Ã— 60 mm perfboard',24,c=muted)
text(45,125,'Opening positions are illustrative; final fit follows the assembled module measurements.',21,c=muted)
text(100,200,'MIC FACE',25,b=True)
text(590,200,'ESP FACE / OPEN CAP',25,b=True)
text(1130,200,'SIDE SECTION',25,b=True)
# front
x,y,X,Y=100,285,445,795
d.rounded_rectangle((x,y,X,Y),22,fill=pale,outline=blue,width=4)
dash((119,321,426,777),'#879da9')
d.ellipse((223,344,323,444),fill='#f3f6fa',outline=teal,width=4)
text(142,470,'Mic sound opening',23,c=teal,b=True)
text(145,632,'40 Ã— 60 perfboard',22,c=muted)
line([(152,795),(393,795)],orange,8)
text(90,825,'USB + battery access at bottom',21,c=orange,b=True)
text(90,865,'Close-fitting body, with only a little',20,c=muted)
text(90,893,'extra length above the board.',20,c=muted)
# rear face
x,y,X,Y=615,285,960,795
d.rounded_rectangle((x,y,X,Y),22,fill='#b7d6e9',outline=blue,width=4)
# 80% wide opening 276/345
sx,sX=649.5,925.5
d.rectangle((sx,280,sX,530),fill='#f3f6fa')
line([(sx,286),(sx,530),(sX,530),(sX,286)],blue,4)
# exposed esp board and chip, schematic
d.rectangle((699,302,875,509),fill='#b2c6be',outline='#6b897e',width=2)
d.rounded_rectangle((726,332,848,445),8,fill='#596974',outline=navy,width=2)
text(749,362,'CHIP',22,c='white',b=True)
text(685,550,'Open to air + wire access',20,c=teal,b=True)
dash((699,532,875,753),'#8197a4')
text(737,646,'ESP below',18,c=muted)
text(733,673,'cap surface',18,c=muted)
for cx,cy in [(633,559),(942,559),(633,774),(942,774)]: d.ellipse((cx-6,cy-6,cx+6,cy+6),fill='#f3f6fa',outline=blue,width=2)
line([(650,252),(925,252)],teal,2)
for xx in [650,925]: line([(xx,246),(xx,258)],teal,2)
text(693,224,'80% of cap width',18,c=teal)
text(590,825,'Deeper opening exposes main chip',21,c=teal,b=True)
text(590,865,'Opening depth and position will match',20,c=muted)
text(590,893,'the actual chip location.',20,c=muted)
# side shell and board
line([(1160,285),(1160,795),(1400,795)],blue,7)
line([(1160,285),(1400,285)],blue,7)
line([(1400,530),(1400,795)],blue,7)
line([(1255,321),(1255,777)],'#a57942',9)
d.rectangle((1267,301,1350,753),fill='#b2c6be',outline='#6b897e',width=2)
d.rectangle((1351,332,1372,445),fill='#596974',outline=navy,width=2)
d.rectangle((1191,350,1249,408),fill='#66b4a0',outline=teal,width=2)
line([(1160,350),(1160,408)],'#f3f6fa',9)
line([(1220,795),(1360,795)],orange,8)
# board top level
line([(1231,321),(1365,321)],orange,2)
text(1125,239,'Small top overhang',20,c=orange,b=True)
text(1414,359,'Air',20,c=teal,b=True)
line([(1420,398),(1375,398)],teal,3)
line([(1384,391),(1375,398),(1384,405)],teal,3)
text(1120,825,'Depth follows your assembly',21,b=True)
text(1120,865,'Small clearance around components;',20,c=muted)
text(1120,893,'edge supports hold the board.',20,c=muted)
line([(45,960),(1550,960)],'#ccd8e2',2)
text(45,985,'Concept only â€” no oversized lower compartment. Final dimensions need the assembled width, length and thickness.',22,b=True)
im.save('outputs/mic_enclosure_concept_v2.png')
