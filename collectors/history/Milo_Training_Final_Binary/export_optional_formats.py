"""Optional .pt/.h5 conversion on the AI teammate's machine; base exports need neither library."""
import argparse
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);p.add_argument('--torch',action='store_true');p.add_argument('--hdf5',action='store_true');a=p.parse_args()
data=np.load(a.dataset,allow_pickle=False)
if a.torch:
    import torch
    torch.save({'X_raw':torch.from_numpy(data['X_raw_channels_first']),
        'X_session_calibrated':torch.from_numpy(data['X_calibrated_channels_first']),
        'y':torch.from_numpy(data['y']),'classes':data['classes'].tolist(),
        'feature_names':data['feature_names'].tolist(),'session_ids':data['session_ids'].tolist(),
        'clip_ids':data['clip_ids'].tolist(),'split_roles':data['split_roles'].tolist()},a.dataset.with_suffix('.pt'))
if a.hdf5:
    import h5py
    with h5py.File(a.dataset.with_suffix('.h5'),'w') as f:
        for k in data.files:
            value=data[k]
            if value.dtype.kind=='U':f.create_dataset(k,data=value.astype(object),dtype=h5py.string_dtype('utf-8'))
            else:f.create_dataset(k,data=value)
if not a.torch and not a.hdf5:p.error('Choose --torch and/or --hdf5; optional dependencies must be installed on the AI machine.')
