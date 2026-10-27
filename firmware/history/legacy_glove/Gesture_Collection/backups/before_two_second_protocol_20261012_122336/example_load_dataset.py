"""Portable input examples; no model architecture is imposed."""
import argparse
import numpy as np
p=argparse.ArgumentParser();p.add_argument('dataset');a=p.parse_args()
data=np.load(a.dataset,allow_pickle=False)
print('Time-major:',data['X_session_calibrated'].shape)  # samples, time, channels
print('Channel-major:',data['X_calibrated_channels_first'].shape)
print('Action-only:',data['X_action_calibrated'].shape)
print('Features:',data['feature_names'])
print('Classes:',data['classes'])
print('Session groups:',np.unique(data['session_ids']))
print('Assigned splits:',{r:int(np.sum(data['split_roles']==r)) for r in np.unique(data['split_roles'])})
# TensorFlow/Keras commonly consumes data['X_session_calibrated'].
# PyTorch Conv1d commonly consumes torch.from_numpy(data['X_calibrated_channels_first']).
# Use data['y'] for integer labels. Fit any global standardiser on TRAIN samples only.
