from pathlib import Path
p=Path('work/build_measured.py').read_text(encoding='utf-8-sig')
p=p.replace('radius=7.3','radius=9.0\nstring_centres=[12.0, W-12.0]\nstring_z=9.8\nstring_radius=2.5')
p=p.replace('def circle_warp(t):','for hx in string_centres:\n subs.append((hx-2.5,L-1.9,string_z-2.5,hx+2.5,L+1,string_z+2.5))\n\ndef circle_warp(t):')
p=p.replace(' return p\nsamples=', ''' # Circular 5 mm bores through the closed top wall, along Y.
 for hx in string_centres:
  dx=p[:,:,0]-hx; dz=p[:,:,2]-string_z
  r=np.maximum(abs(dx),abs(dz));rr=np.hypot(dx,dz)
  mask=(r>=2.5-1e-8)&(r<4.5)&(rr>0)&(p[:,:,1]>=L-1.9-1e-8)
  f=np.ones_like(r);f[mask]=1+(4.5-r[mask])/2*(2.5/rr[mask]-1)
  p[:,:,0]=hx+dx*f;p[:,:,2]=string_z+dz*f
 return p
samples=''')
p=p.replace("housing=mesh(adds,subs,([cx+v for v in samples],[cy+v for v in samples],[]),circle_warp)","hole_samples=sorted(set([-4.5,4.5]+list(np.linspace(-2.5,2.5,25))))\nhousing=mesh(adds,subs,([cx+v for v in samples]+[hx+v for hx in string_centres for v in hole_samples],[cy+v for v in samples],[string_z+v for v in hole_samples]),circle_warp)")
p=p.replace('MEASURED_v2','NECKLACE_v3').replace('Measured_v2','Necklace_v3').replace('measured_enclosure_meshes','necklace_enclosure_meshes').replace('MEASURED ENCLOSURE V2','NECKLACE ENCLOSURE V3').replace('diameter 14.6','diameter 18.0')
p=p.replace('PRINT AND FIT\n','NECKLACE HOLES\nTwo 5 mm diameter bores through the closed top end wall.\nAxes run along the module length (Y). Centres X=12 and 32.85, Z=9.8.\nHole centre spacing: 20.85 mm. Thread cord before inserting electronics.\nThe closed wall is 1.8 mm thick; printed cord retention strength is untested.\n\nPRINT AND FIT\n')
p=p.replace('# Cap assembly: printed cap Z points towards cavity; mirrored Y to preserve top edge.','# Cap assembly: turn printed cap over about its length axis; its geometry is symmetric across width.')
Path('work/build_necklace.py').write_text(p,encoding='utf-8')
