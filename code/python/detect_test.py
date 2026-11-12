"""
VisionBot - ArUco detection test (Day 1, Block 4 of the build plan)

What it does
  - opens the webcam and shows the live image
  - draws a box + ID label around every ArUco marker it recognises
    (green = robot ID 10, blue = destination card ID 20)
  - when BOTH markers are visible:
      * draws the robot -> target line
      * shows the pixel distance (and cm if you pass --scale)
      * shows the line angle and the robot marker's heading (yaw)

Keys
  s        save an annotated snapshot (goes into snapshots/, use it in the log)
  q / ESC  quit

How to run (from the code/python folder)
  python detect_test.py                    # camera 0, pixels only
  python detect_test.py --cam 1            # if camera 0 is not the Logitech
  python detect_test.py --scale 0.05       # after measuring cm-per-pixel
  python detect_test.py --flip             # overhead camera mounted upside down

Numbers to record for the project log (Block 4):
  1. px->cm scale: put the two markers exactly 30 cm apart (ruler!),
     scale = 30 / pixel-distance shown on screen
  2. robot yaw when the robot points N, E, S, W
     (tomorrow we use these 4 numbers to fix left/right and sign conventions)
"""

import argparse
import os
import time

import cv2
import numpy as np

ROBOT_ID = 10     # marker on top of the robot
TARGET_ID = 20    # marker on the destination card
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")

# colours (OpenCV uses BGR, not RGB)
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
    in the MARKER's frame. Note: image y grows DOWNWARDS, so 0 deg = right
    and 90 deg = downwards on screen. That is fine - the Block 4 yaw check
    (robot pointing N/E/S/W) tells us the real-world directions.
    """
    c = corner.reshape(4, 2)
    mid_top = (c[0] + c[1]) / 2.0
    u = mid_top - center_of(corner)
    return float(np.degrees(np.arctan2(u[1], u[0])))


# --------------------------------------------------------------- drawing
def label(img, text, x, y, color):
    cv2.putText(img, text, (int(x), int(y)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)


def main():
    ap = argparse.ArgumentParser(description="VisionBot ArUco detection test")
    ap.add_argument("--cam", type=int, default=0, help="camera index (default 0)")
    ap.add_argument("--scale", type=float, default=None,
                    help="cm per pixel, e.g. 0.05 - adds cm to the readouts")
    ap.add_argument("--flip", action="store_true",
                    help="rotate the image 180 deg (overhead camera upside down)")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.cam, cv2.CAP_DSHOW)   # CAP_DSHOW opens faster on Windows
    if not cap.isOpened():
        cap = cv2.VideoCapture(args.cam)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera {args.cam}. Try --cam 1 or --cam 2.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)           # ask for full HD
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    try:                                              # stop autofocus hunting
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)            # (focus stays where it was)
    except Exception:
        pass

    detector = ArucoDetector()
    print(f"Camera {args.cam} open. Looking for marker {ROBOT_ID} (robot) and "
          f"{TARGET_ID} (target).  Keys: s=snapshot, q/ESC=quit")

    fps, last_time, last_print = 0.0, time.time(), 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            raise SystemExit("Camera stopped sending frames.")

        if args.flip:
            frame = cv2.rotate(frame, cv2.ROTATE_180)

        found = detector.detect(frame)

        # --- draw every visible marker
        for marker_id, corner in found.items():
            color = C_ROBOT if marker_id == ROBOT_ID else C_TARGET
            pts = corner.reshape(4, 2).astype(int)
            cv2.polylines(frame, [pts], True, color, 3)
            cx, cy = center_of(corner)
            cv2.circle(frame, (int(cx), int(cy)), 6, color, -1)
            label(frame, f"ID {marker_id}", pts[0][0], pts[0][1] - 12, color)

        # --- when both markers are visible, do the navigation preview
        if ROBOT_ID in found and TARGET_ID in found:
            r = center_of(found[ROBOT_ID])
            t = center_of(found[TARGET_ID])
            cv2.line(frame, r.astype(int), t.astype(int), C_LINE, 3)

            dist_px = float(np.hypot(t[0] - r[0], t[1] - r[1]))
            line_deg = float(np.degrees(np.arctan2(t[1] - r[1], t[0] - r[0])))
            yaw = yaw_deg(found[ROBOT_ID])

            mid = ((r[0] + t[0]) / 2, (r[1] + t[1]) / 2 - 15)
            text = f"{dist_px:.0f} px" + (f" = {dist_px * args.scale:.1f} cm"
                                          if args.scale else "")
            label(frame, text, *mid, C_LINE)
            label(frame, f"line {line_deg:.0f} deg  robot yaw {yaw:.0f} deg",
                  mid[0], mid[1] + 30, C_LINE)

            now = time.time()
            if now - last_print > 0.5:                # console readout, 2x/sec
                last_print = now
                cm = f" = {dist_px * args.scale:.1f} cm" if args.scale else ""
                print(f"robot=({r[0]:.0f},{r[1]:.0f}) target=({t[0]:.0f},{t[1]:.0f}) "
                      f"dist={dist_px:.0f} px{cm}  line={line_deg:.1f}  yaw={yaw:.1f}")
        else:
            now = time.time()
            if now - last_print > 0.5:
                last_print = now
                print(f"visible IDs: {sorted(found)} "
                      f"(waiting for both {ROBOT_ID} and {TARGET_ID})")

        # --- fps + help strip
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_time, 1e-6))
        last_time = now
        cv2.rectangle(frame, (0, 0), (560, 42), (255, 255, 255), -1)
        cv2.putText(frame, f"{fps:.0f} fps   s=snapshot  q/ESC=quit", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 40), 2)

        cv2.imshow("VisionBot - detection test", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):                     # q or ESC
            break
        if key == ord("s"):                           # snapshot for the logbook
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            path = os.path.join(SNAPSHOT_DIR,
                                time.strftime("snap_%Y%m%d_%H%M%S.png"))
            cv2.imwrite(path, frame)
            print(f"snapshot saved: {path}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
