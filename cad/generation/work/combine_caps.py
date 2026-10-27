import struct
from pathlib import Path
import numpy as np
out=Path(r'C:\Users\nitin\Documents\Codex\2026-10-06\cod\outputs')
def read(p):
 b=Path(p).read_bytes(); n=struct.unpack_from('<I',b,80)[0]
 return np.array([struct.unpack_from('<12f',b,84+50*i)[3:] for i in range(n)],dtype=float).reshape(-1,3,3)
h=read(r'C:\Users\nitin\Downloads\LiPo_600mAh_slide_sleeve.stl'); h-=h.min(axis=(0,1))
c=read(out/'LiPo_600mAh_cap_standard.stl'); c-=c.min(axis=(0,1))
parts=[h,c+[36.2,0,0],c+[36.2,21.5,0]]
t=np.concatenate(parts)
p=out/'LiPo_1_housing_2_caps.stl'
with p.open('wb') as f:
 f.write(b'One original battery sleeve and two standard caps; units mm'.ljust(80,b' ')); f.write(struct.pack('<I',len(t)))
 for a in t:
  n=np.cross(a[1]-a[0],a[2]-a[0]); n/=np.linalg.norm(n)
  f.write(struct.pack('<12fH',*n,*a.flatten(),0))
assert len(read(p))==252+2*172
for i,a in enumerate(parts):
 assert abs(a[:,:,2].min())<1e-6
 for other in parts[i+1:]:
  assert any(a.max(axis=(0,1))[j]<other.min(axis=(0,1))[j] or other.max(axis=(0,1))[j]<a.min(axis=(0,1))[j] for j in [0,1])
print('Saved:',p)
print('3 separated parts, all on bed; dimensions (mm):',t.max(axis=(0,1)).round(2).tolist())
