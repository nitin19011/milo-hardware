"""0.8-second features. Raw-flex deltas are local detector hints, not transmitted AI inputs."""
import numpy as np

WINDOW = 40
STEP = 5
RAW_SPANS = np.array([436.5, 613.5, 120.5], dtype=np.float64)
AXES = ("ax", "ay", "az", "gx", "gy", "gz")
FEATURE_NAMES = ([f"{name}_{stat}" for stat in ("mean", "std", "range", "mean_abs_diff") for name in AXES]
    + ["gyro_norm_mean", "gyro_norm_std", "gyro_norm_max", "accel_norm_std", "accel_norm_range", "accel_norm_mean_abs_diff"]
    + [f"{name}_{stat}" for stat in ("last", "fraction_bent", "transitions") for name in ("thumb", "index", "middle")]
    + [f"{name}_raw_{stat}" for stat in ("relative_range", "relative_mean_abs_diff") for name in ("thumb", "index", "middle")])


def features(window):
    a = np.asarray(window, dtype=np.float64)
    if a.shape != (40, 12): raise ValueError("Expected 40 rows of six SI axes, three states and three raw ADC values")
    imu, states, raw = a[:, :6], a[:, 6:9], a[:, 9:12]
    g, acc = np.linalg.norm(imu[:, 3:6], axis=1), np.linalg.norm(imu[:, :3], axis=1)
    result = np.concatenate((imu.mean(axis=0), imu.std(axis=0), np.ptp(imu, axis=0), np.abs(np.diff(imu, axis=0)).mean(axis=0),
        [g.mean(), g.std(), g.max(), acc.std(), np.ptp(acc), np.abs(np.diff(acc)).mean()],
        states[-1], states.mean(axis=0), np.count_nonzero(np.diff(states, axis=0), axis=0),
        np.ptp(raw, axis=0)/RAW_SPANS, np.abs(np.diff(raw, axis=0)).mean(axis=0)/RAW_SPANS))
    return (np.floor(result * 10000.0 + .5) / 10000.0).astype(np.float32)


def activity(x):
    return x[:, 24] + 2*x[:, 27]/9.80665 + 2*x[:, 39:42].sum(axis=1)
