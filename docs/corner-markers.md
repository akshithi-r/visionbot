# Corner Markers (IDs 30–33) — Placement Guide

The four ~6 cm markers from **page 3** of `code/python/markers/print_a4_markers.pdf`.

## What they do

The camera is never perfectly centered/perpendicular, so raw pixels lie a little
(one cm near the camera ≠ one cm far away; angles warp). The four corners let
the software compute a **perspective correction (homography)** every frame:

- true cm positions anywhere in the arena
- **self-healing** — camera bumped at the venue? next frame recalculates, no fix needed
- fallback if corners are missing: single ruler px→cm scale (works for a
  centered overhead rig — the demo never depends on the corners)

## Placement rules (what matters)

1. **Order, as the CAMERA sees it:**
   - **ID 30 = top-left · ID 31 = top-right · ID 32 = bottom-right · ID 33 = bottom-left**
   - Wrong order = mirrored coordinates = robot drives the wrong way → re-tape.
2. Each marker **near its arena corner**, flat (no curls), all four visible in
   the camera at the same time.
3. **10-second check:** stand the robot next to ID 30 — it must appear in the
   **top-left** of the picture. Repeat mentally for 32 (bottom-right).

## What does NOT matter

- Exact distances between markers — the homography learns the real geometry
  from wherever they are.
- Perfect squareness or symmetry.

## One-time measurement (for true cm readouts)

With a ruler, measure **between the taped markers**:

- long side (30↔31 or 33↔32): ____ cm
- short side (30↔33 or 31↔32): ____ cm

Write these two numbers into `docs/project-log.md` — `main.py` uses them.
If the markers ever move on the board, re-measure (or better: **tape them
permanently to the board** so the numbers stay valid forever).

## Demo-day reminder

The arena board with taped corners travels as one piece. At the venue: set the
rig, open the detection window, confirm all four corner IDs + both markers
show green — part of the 2-minute acceptance test in the build plan.
