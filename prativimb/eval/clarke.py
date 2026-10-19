"""Clarke error grid zone assignment (Clarke et al., Diabetes Care 1987), mg/dL."""
from __future__ import annotations

import numpy as np


def zones(ref: np.ndarray, pred: np.ndarray) -> np.ndarray:
    ref = np.asarray(ref, float)
    pred = np.asarray(pred, float)
    z = np.full(ref.shape, "B", dtype="<U1")
    a = ((ref <= 70) & (pred <= 70)) | (np.abs(pred - ref) <= 0.2 * ref)
    e = ((ref >= 180) & (pred <= 70)) | ((ref <= 70) & (pred >= 180))
    c = ((ref >= 70) & (ref <= 290) & (pred >= ref + 110)) | ((ref >= 130) & (ref <= 180) & (pred <= (7 / 5) * ref - 182))
    d = ((ref >= 240) & (pred >= 70) & (pred <= 180)) | ((ref <= 175 / 3) & (pred <= 180) & (pred >= 70)) | \
        ((ref >= 175 / 3) & (ref <= 70) & (pred >= (6 / 5) * ref))
    z[d] = "D"
    z[c] = "C"
    z[e] = "E"
    z[a] = "A"
    return z


def zone_table(ref: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    z = zones(ref, pred)
    return {k: float(np.mean(z == k) * 100) for k in "ABCDE"}
