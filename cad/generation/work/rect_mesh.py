"""Exact axis-aligned union/subtraction meshing, with matching subdivisions."""
import numpy as np

def rect_mesh(add,sub=(),extra=((),(),()),warp=None,keep=()):
 axes=[np.array(sorted(set(round(float(v),6) for v in ([b[k] for b in list(add)+list(keep)]+[b[k+3] for b in list(add)+list(keep)]+[b[k] for b in sub]+[b[k+3] for b in sub]+list(extra[k]))))) for k in range(3)]
 mid=[(v[:-1]+v[1:])/2 for v in axes]
 occ=np.zeros(tuple(len(v) for v in mid),bool)
 def region(b):
  return tuple(slice(np.searchsorted(mid[k],b[k],side='right'),np.searchsorted(mid[k],b[k+3],side='left')) for k in range(3))
 for b in add:occ[region(b)]=True
 for b in sub:occ[region(b)]=False
 for b in keep:occ[region(b)]=True
 # Outward-oriented corners on six box faces.
 offsets=[[(0,0,0),(0,0,1),(0,1,1),(0,1,0)],[(1,0,0),(1,1,0),(1,1,1),(1,0,1)],[(0,0,0),(1,0,0),(1,0,1),(0,0,1)],[(0,1,0),(0,1,1),(1,1,1),(1,1,0)],[(0,0,0),(0,1,0),(1,1,0),(1,0,0)],[(0,0,1),(1,0,1),(1,1,1),(0,1,1)]]
 chunks=[]
 for direction in range(6):
  axis=direction//2;positive=direction%2
  adjacent=np.zeros_like(occ)
  dst=[slice(None)]*3;src=[slice(None)]*3
  dst[axis]=slice(None,-1) if positive else slice(1,None)
  src[axis]=slice(1,None) if positive else slice(None,-1)
  adjacent[tuple(dst)]=occ[tuple(src)]
  ids=np.argwhere(occ&~adjacent)
  if not len(ids):continue
  q=np.stack([np.column_stack([axes[k][ids[:,k]+corner[k]] for k in range(3)]) for corner in offsets[direction]],axis=1)
  chunks.extend([q[:,[0,1,2]],q[:,[0,2,3]]])
 t=np.concatenate(chunks)
 return warp(t) if warp else t

