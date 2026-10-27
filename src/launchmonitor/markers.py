"""Club-face marker sticker: the one definition shared by the printable sheet, the
simulator, the detector and the solver.

Coordinates are on the face, in metres: u toward the toe, v up the face, origin at the
face centre (where the ball is struck). The sticker (32 x 28.5 mm) starts 3.5 mm toe-side
of the centre and reaches 35.5 mm toward the toe: clear of a centred strike, within an iron's
toe, and facing the cameras, which sit on the toe side.

Five 5 mm dots in an irregular layout, chosen by search so that no wrong assignment of
dots fits the layout under any stretch or skew a camera can produce (the cameras see the
face very obliquely, so distances alone are not enough), with all five dots or with any
one missing (glare, the ball in the way). The best wrong fit is 1.2 mm rms off;
tests/test_club.py checks this stays above 1 mm. The dots are 5 mm because
the 2-camera rig sees the face at a steep angle: a 3 mm dot would be only ~3 px wide.
Changing this layout means reprinting the stickers (tools/export_cad.py).
"""

from __future__ import annotations

import numpy as np

FACE_MARKERS_UV = np.array([[0.009, -0.0075], [0.0095, 0.007], [0.030, 0.008], [0.0175, -0.003], [0.0255, -0.0095]])
DOT_DIAMETER_M = 0.005
STICKER_MARGIN_M = 0.003

# Sticker outline (u0, v0, u1, v1): dots plus a margin of white all round.
STICKER_RECT = (
    float(FACE_MARKERS_UV[:, 0].min() - DOT_DIAMETER_M / 2 - STICKER_MARGIN_M),
    float(FACE_MARKERS_UV[:, 1].min() - DOT_DIAMETER_M / 2 - STICKER_MARGIN_M),
    float(FACE_MARKERS_UV[:, 0].max() + DOT_DIAMETER_M / 2 + STICKER_MARGIN_M),
    float(FACE_MARKERS_UV[:, 1].max() + DOT_DIAMETER_M / 2 + STICKER_MARGIN_M),
)
