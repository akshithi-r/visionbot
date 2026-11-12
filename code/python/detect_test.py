"""
VisionBot - ArUco detection test, NATIVE window (no browser, no Gradio)

The simplest possible pipeline, all in one main-thread loop:
  camera -> detect -> draw -> window. Nothing in between to break.

  - green box = robot marker (ID 10), blue box = destination card (ID 20)
  - magenta line robot -> target, with pixel/cm distance
  - banner: "BOTH MARKERS DETECTED" when both are visible
  - console shows camera pick + frame brightness (0-10 = black frames)

Keys
  s        save annotated snapshot to snapshots/
  q / ESC  quit

Run (from the code/python folder):
  python detect_test.py                    # auto-detects the 1080p webcam
  python detect_test.py --scale 0.05       # show cm too (Block 4 calibration)
  python detect_test.py --flip             # overhead camera upside down
  python detect_test.py --cam 1            # force a specific camera index

This module is also a library: detect_ui.py imports ArucoDetector,
center_of and yaw_deg from here - keep those names intact.

Numbers to record for the project log (Block 4):
  1. px->cm scale: markers exactly 30 cm apart, scale = 30 / pixel distance
  2. robot yaw when pointing N, E, S, W (for navigation sign conventions)
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

ROBOT_ID = 10     # marker on top of the robot
TARGET_ID = 20    # marker on the destination card
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
IS_WINDOWS = sys.platform.startswith("win")
DRAIN_N = 4       # stale buffered frames to skip per loop (keeps video fresh)

# colours in BGR (what OpenCV paints with)
C_ROBOT = (0, 220, 0)      # green
C_TARGET = (255, 120, 0)   # blue
C_LINE = (255, 0, 255)     # magenta


# --------------------------------------------------------------- detection
class ArucoDetector:
    """Thin wrapper so the code works on old and new OpenCV versions."""

    def __init__(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params = cv2.aruco.DetectorParameters()
        if hasattr(cv2.aruco, "ArucoDetector"):            # OpenCV 4.7+
            self._detector = cv2.aruco.ArucoDetector(dictionary, params)
            self._legacy = None
        else:                                              # very old installs
            self._detector = dictionary
            self._legacy = params

    def detect(self, frame):
        """Returns {marker_id: corners(4x2 array)} for everything found."""
        if self._legacy is None:
            corners, ids, _ = self._detector.detectMarkers(frame)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(
                frame, self._detector, parameters=self._legacy)
        found = {}
        if ids is not None:
            for marker_id, corner in zip(ids.flatten(), corners):
                found[int(marker_id)] = corner
        return found


# --------------------------------------------------------------- geometry
def center_of(corner):
    """Centre point (x, y) of one marker."""
    return corner.reshape(4, 2).mean(axis=0)


def yaw_deg(corner):
    """Which way the marker's own 'top' edge points, in degrees.

    Corners arrive ordered: top-left, top-right, bottom-right, bottom-left
    in the MARKER's frame. Image y grows DOWNWARDS, so 0 deg = right and
    90 deg = down on screen. The Block 4 yaw check (robot pointing N/E/S/W)
    converts these to real-world directions.
    """
    c = corner.reshape(4, 2)
    mid_top = (c[0] + c[1]) / 2.0
    u = mid_top - center_of(corner)
    return float(np.degrees(np.arctan2(u[1], u[0])))


# --------------------------------------------------------------- camera
def open_camera_once(idx):
    """Open camera idx, DirectShow on Windows / V4L2 on Linux (both PROVEN).
    Returns a working VideoCapture or None."""
    cap = cv2.VideoCapture()
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2500)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2500)
    cap.open(idx, cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[camera] index {idx}: cannot open")
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    try:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)                # stop focus hunting
    except Exception:
        pass
    ok, _ = cap.read()
    if not ok:
        print(f"[camera] index {idx}: opened but no frame")
        cap.release()
        return None
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[camera] index {idx} ok ({w}x{h})")
    return cap


def open_camera_auto():
    """Probe indices 0..2, prefer the camera that reports 1920x1080
    (our Logitech C920 - the only 1080p camera; Windows re-numbers
    cameras across reboots/replugs, so we never trust a fixed index)."""
    fallback = None
    for idx in range(3):
        cap = open_camera_once(idx)
        if cap is None:
            continue
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        if w >= 1920:
            return cap                               # the C920 - done
        if fallback is None:
            fallback = cap                           # remember first working
        else:
            cap.release()
    if fallback is not None:
        print("[camera] no 1080p camera found - using first working camera")
    return fallback


def drain_read(cap, n=DRAIN_N):
    """Skip n queued (stale) frames, decode and return the newest one.
    grab() is cheap (no decode) - keeps the window live at any loop rate."""
    for _ in range(n):
        if not cap.grab():
            return None
    ok, frame = cap.retrieve()
    return frame if ok else None


# --------------------------------------------------------------- drawing
def banner(frame, text, ok):
    """Big status banner, top centre of the window."""
    h = frame.shape[0]
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    x0 = (frame.shape[1] - tw) // 2
    color = (30, 143, 31) if ok else (90, 90, 90)     # green / gray (BGR)
    cv2.rectangle(frame, (x0 - 15, 12), (x0 + tw + 15, 40 + th), color, -1)
    cv2.putText(frame, text, (x0, 35 + th // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)


def annotate(frame, found, scale):
    """Draw boxes/labels/line on one frame. Returns nav info or None."""
    for marker_id, corner in found.items():
        color = C_ROBOT if marker_id == ROBOT_ID else C_TARGET
        pts = corner.reshape(4, 2).astype(int)
        cv2.polylines(frame, [pts], True, color, 3)
        cx, cy = center_of(corner)
        cv2.circle(frame, (int(cx), int(cy)), 6, color, -1)
        cv2.putText(frame, f"ID {marker_id}", (pts[0][0], pts[0][1] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    if ROBOT_ID in found and TARGET_ID in found:
        r, t = center_of(found[ROBOT_ID]), center_of(found[TARGET_ID])
        cv2.line(frame, r.astype(int), t.astype(int), C_LINE, 3)
        dist_px = float(np.hypot(t[0] - r[0], t[1] - r[1]))
        line_deg = float(np.degrees(np.arctan2(t[1] - r[1], t[0] - r[0])))
        yaw = yaw_deg(found[ROBOT_ID])
        txt = f"{dist_px:.0f} px" + (f" = {dist_px * scale:.1f} cm" if scale else "")
        mid = (int((r[0] + t[0]) / 2), int((r[1] + t[1]) / 2))
        cv2.putText(frame, txt, (mid[0], mid[1] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, C_LINE, 2)
        cv2.putText(frame, f"line {line_deg:.0f} deg  yaw {yaw:.0f} deg",
                    (mid[0], mid[1] + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, C_LINE, 2)
        return {"dist_px": dist_px, "line_deg": line_deg, "yaw": yaw,
                "r": r, "t": t}
    return None


# --------------------------------------------------------------- main loop
def main():
    ap = argparse.ArgumentParser(description="VisionBot ArUco detection test")
    ap.add_argument("--cam", type=int, default=None,
                    help="camera index; omit to auto-detect the 1080p webcam")
    ap.add_argument("--scale", type=float, default=None,
                    help="cm per pixel, e.g. 0.05")
    ap.add_argument("--flip", action="store_true",
                    help="rotate the image 180 degrees")
    args = ap.parse_args()

    if args.cam is not None:
        cap = open_camera_once(args.cam)
    else:
        print("[camera] auto-detecting (looking for the 1080p webcam)...")
        cap = open_camera_auto()
    if cap is None:
        raise SystemExit("No camera available. Try --cam 0 / --cam 1.")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cam_info = f"camera {args.cam if args.cam is not None else 'auto'} ({w}x{h})"
    print(f"[camera] using {cam_info}")
    print("Keys: s = snapshot, q / ESC = quit")

    detector = ArucoDetector()
    fps, t_prev, t_frame_dbg = 0.0, time.time(), 0.0

    while True:
        frame = drain_read(cap)
        if frame is None:
            print("[camera] frame lost - stopping")
            break

        if args.flip:
            frame = cv2.rotate(frame, cv2.ROTATE_180)

        found = detector.detect(frame)
        info = annotate(frame, found, args.scale)

        both = ROBOT_ID in found and TARGET_ID in found
        banner(frame, "BOTH MARKERS DETECTED" if both else "waiting for both markers...",
               both)

        # HUD strip, top-left
        now = time.time()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)
        t_prev = now
        robot_state = "ROBOT OK" if ROBOT_ID in found else "ROBOT lost"
        target_state = "TARGET OK" if TARGET_ID in found else "TARGET lost"
        cv2.rectangle(frame, (0, h - 90), (620, h), (255, 255, 255), -1)
        cv2.putText(frame, f"{cam_info}   {fps:.0f} fps   s=snapshot  q=quit",
                    (10, h - 62), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 40), 2)
        cv2.putText(frame, f"{robot_state}   {target_state}"
                    + (f"   dist {info['dist_px']:.0f} px" if info else ""),
                    (10, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 40), 2)

        # console diagnostic: brightness ~0 = black frames (shutter/driver)
        if now - t_frame_dbg > 3:
            t_frame_dbg = now
            print(f"[frame] {frame.shape[1]}x{frame.shape[0]} "
                  f"mean brightness={frame.mean():.0f} fps={fps:.0f}")

        cv2.imshow("VisionBot - detection test (s=snapshot, q=quit)", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("s"):
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            path = os.path.join(SNAPSHOT_DIR,
                                time.strftime("snap_%Y%m%d_%H%M%S.png"))
            cv2.imwrite(path, frame)
            print(f"snapshot saved: {path}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
