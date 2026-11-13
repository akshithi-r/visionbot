"""
VisionBot - MAIN: camera-guided autonomous navigation (Day 2, Block 5)

The closed loop, all visible in one window:
  camera -> ArUco detect -> cm positions (corner markers 30-33) ->
  turn / drive / stop decision -> UDP to the robot -> repeat 10x/sec

UI (CustomTkinter):
  START (or SPACE)   begin autonomous run      PAUSE           stop sending
  E-STOP (or ESC)    emergency stop burst      Speed slider    constant drive/turn speed
  Turn invert        flip turn direction if the robot turns AWAY from the card
  Heading offset     fixes a marker taped slightly rotated (degrees)
  Arena W x H        cm between the taped corner markers (one-time ruler job)
  cm/px              fallback ruler scale (used only if no corner markers)

Behaviour (deliberately simple - docs/plan-2day-build.md):
  turn in place until facing the card (+/- angle tol) -> straight -> stop within
  stop tolerance. Marker lost -> hold ~3 frames -> STOP. Arrived -> latch until
  the card moves again. Radio silent -> the robot's own deadman stops it (0.6 s).

Camera rule on this project (learned the hard way): the UI thread must NEVER
call cv2.VideoCapture - a single open() can hang FOREVER on a wedged driver
(the timeout props don't fire), and Windows then flags the window "not
responding". So all camera work happens in a separate HELPER PROCESS that
ships JPEG frames over a queue; a hang there is caught by a watchdog in the
UI, the helper gets killed and can respawn. Only the 1080p C920 is ever used
(demo rule - the integrated webcam is skipped, never substituted).

Run:  .venv\\Scripts\\python main.py        (Windows)
      .venv/bin/python main.py             (Ubuntu demo box)
Robot Wi-Fi "VisionBot" joined first, robot powered, camera rig up.
"""

import math
import multiprocessing as mp
import os
import socket
import sys
import time
from collections import deque

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_test import (ArucoDetector, center_of, yaw_deg,
                         open_camera_once, ROBOT_ID, TARGET_ID, SNAPSHOT_DIR)

import customtkinter as ctk
from PIL import Image, ImageTk

# ---- radio / loop constants (match the firmware) ----
ROBOT_IP = "192.168.4.1"
ROBOT_PORT = 5005
SEND_HZ = 10            # command rate - also feeds the firmware deadman

# ---- marker IDs ----
CORNER_IDS = (30, 31, 32, 33)   # TL, TR, BR, BL as the camera sees them

# ---- overlay colours (BGR) ----
C_ROBOT = (0, 220, 0)
C_TARGET = (255, 120, 0)
C_LINE = (255, 0, 255)
C_CORNER = (255, 220, 0)
C_ARROW = (0, 180, 255)


def wrap180(a):
    """Wrap an angle difference into -180..+180."""
    return (a + 180.0) % 360.0 - 180.0


# =========================================================== radio link
class RobotLink:
    """UDP link to the robot. Protocol (firmware src/main.cpp):
    'F'/'B'/'L'/'R'/'S' moves, 'V<0-1023>' sets speed."""

    def __init__(self, ip, port):
        self.addr = (ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sent = 0

    def send(self, msg):
        self.sock.sendto((msg + "\n").encode(), self.addr)
        self.sent += 1

    def send_speed(self, v):
        self.send(f"V{int(v)}")

    def stop_burst(self, n=5):
        """A burst of STOPs so the robot parks even with packet loss."""
        for _ in range(n):
            self.send("S")
            time.sleep(0.03)

    def close(self):
        self.sock.close()


# =========================================================== camera feed
def camera_worker(cmd_q, evt_q, frame_q):
    """HELPER PROCESS - the only place cv2.VideoCapture is ever touched.

    Runs in its own process on purpose: an open() on a wedged driver can
    block FOREVER (proven on this project), and then it only takes down
    this helper - the UI keeps running, shows a watchdog message, and can
    kill + respawn us. Commands: ('open', [indices]) / ('close',) /
    ('quit',). Events out: ('opening',i) ('skip',i,w) ('ok',i,w,h)
    ('fail',) ('closed',) ('frameerr',). Frames out: JPEG bytes.
    """
    cap = None
    while True:
        cmd = None
        try:
            cmd = cmd_q.get_nowait()
        except Exception:
            pass

        if cmd is not None:
            kind = cmd[0]
            if kind == "open":
                if cap is not None:
                    cap.release()
                    cap = None
                for idx in cmd[1]:
                    evt_q.put(("opening", idx))
                    cap = open_camera_once(idx)          # may block forever - fine here
                    if cap is not None:
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        if w >= 1920:                    # the C920
                            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            evt_q.put(("ok", idx, w, h))
                            break
                        cap.release()                    # not 1080p - skip it
                        evt_q.put(("skip", idx, w))
                if cap is None:
                    evt_q.put(("fail",))
            elif kind == "close":
                if cap is not None:
                    cap.release()
                    cap = None
                evt_q.put(("closed",))
            elif kind == "quit":
                break

        if cap is None:
            if cmd is None:
                time.sleep(0.02)                         # idle - nothing to do
            continue

        ok, frame = cap.read()
        if ok:
            ok2, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok2:
                data = buf.tobytes()
                try:
                    frame_q.put_nowait(data)
                except Exception:                        # queue full -> drop oldest
                    try:
                        frame_q.get_nowait()
                        frame_q.put_nowait(data)
                    except Exception:
                        pass
        else:
            evt_q.put(("frameerr",))                     # stream stalled
            time.sleep(0.1)

    if cap is not None:
        cap.release()


class CameraFeed:
    """UI-side handle for the camera helper process.

    The UI thread only ever drains queues and decodes JPEGs - nothing here
    can block, so the window can no longer freeze on camera problems.
    """

    OPEN_STUCK_S = 15.0    # no news from the helper while opening = wedged

    def __init__(self):
        self._mp = mp.get_context("spawn")
        self.proc = None
        self.cmd_q = self.evt_q = self.frame_q = None
        self.opening = False
        self.last_msg = 0.0

    def _ensure_worker(self):
        if self.proc is not None and self.proc.is_alive():
            return
        self.cmd_q = self._mp.Queue()
        self.evt_q = self._mp.Queue()
        self.frame_q = self._mp.Queue(maxsize=2)
        self.proc = self._mp.Process(target=camera_worker,
                                     args=(self.cmd_q, self.evt_q, self.frame_q),
                                     daemon=True)
        self.proc.start()

    def start_open(self, indices):
        self._ensure_worker()
        self.opening = True
        self.last_msg = time.monotonic()
        self.cmd_q.put(("open", list(indices)))

    def poll(self):
        """Drain status events; adds ('stuck',)/('dead',) verdicts."""
        events = []
        if self.proc is None:
            return events
        while True:
            try:
                ev = self.evt_q.get_nowait()
            except Exception:
                break
            self.last_msg = time.monotonic()
            if ev[0] in ("ok", "fail"):
                self.opening = False
            events.append(ev)
        if self.opening:
            if time.monotonic() - self.last_msg > self.OPEN_STUCK_S:
                events.append(("stuck",))
                self.opening = False
            elif not self.proc.is_alive():
                events.append(("dead", self.proc.exitcode))
                self.opening = False
        return events

    def latest_frame(self):
        """Newest JPEG from the helper, decoded. None if nothing new."""
        data = None
        while True:
            try:
                data = self.frame_q.get_nowait()
            except Exception:
                break
        if data is None:
            return None
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    def shutdown(self):
        """Stop the camera and end the helper. Safe to call anytime."""
        self.opening = False
        if self.proc is None:
            return
        if self.proc.is_alive():
            try:
                self.cmd_q.put(("quit",))
            except Exception:
                pass
            self.proc.join(timeout=1.5)      # let it release() the camera
        if self.proc.is_alive():
            self.proc.terminate()            # wedged helper - force it
            self.proc.join(timeout=2.0)
        self.proc = None


# =========================================================== arena mapping
class ArenaMap:
    """Pixel -> true-cm mapping, derived from the four taped corner markers.

    NOTHING is typed by hand: each corner marker's printed size is known
    (CORNER_MARKER_CM), the detector gives its 4 corners in pixels, so the
    cm/px scale falls out - 4 markers x 4 sides = 16 samples averaged per
    frame (~1% error, self-updating, survives camera bumps).

    All four corners visible -> homography recomputed THIS frame. Robot
    covering one corner -> cached last-good homography. No corners ever
    -> typed ruler scale (or the last marker-derived scale if we had one).
    """

    SCALE_SMOOTH = 0.25  # EMA factor for the marker-derived cm/px scale

    def __init__(self, corner_marker_cm=6.0, cm_per_px=0.05):
        self.corner_marker_cm = float(corner_marker_cm)
        self.cm_per_px = float(cm_per_px)
        self.width_override = None   # typed true frame size (cm), None = auto
        self.height_override = None
        self.auto_w = 0.0            # marker-derived sizes (for comparison)
        self.auto_h = 0.0
        self.width_cm = 0.0
        self.height_cm = 0.0
        self.last_scale = None       # cm/px derived from the markers (cached)
        self.H = None                # live homography this frame
        self.last_good_H = None      # cache while a corner is hidden
        self.corner_error = None     # "mirrored" if 30-33 taped in wrong order

    def configure(self, corner_marker_cm, cm_per_px,
                  width_override=None, height_override=None):
        self.corner_marker_cm = float(corner_marker_cm)
        self.cm_per_px = float(cm_per_px)
        self.width_override = width_override
        self.height_override = height_override

    def update(self, found):
        """Call once per frame with all detected markers."""
        if all(cid in found for cid in CORNER_IDS):
            centers = np.array([center_of(found[cid]) for cid in CORNER_IDS],
                               dtype=np.float32)
            # Sanity: 30->31->32->33 must run around the quad the SAME way
            # as the destination rectangle. A mirrored taping (e.g. two
            # corners swapped as the camera sees them) passes detection but
            # flips the whole navigation frame -> random turning. Shoelace
            # sign tells us: it must be positive like the dst rectangle.
            shoelace = 0.0
            for i in range(4):
                x1, y1 = centers[i]
                x2, y2 = centers[(i + 1) % 4]
                shoelace += x1 * y2 - x2 * y1
            if shoelace <= 0:
                self.corner_error = "mirrored"
                self.H = None        # refuse the bad frame (scale fallback)
                return
            self.corner_error = None
            sides = []
            for cid in CORNER_IDS:
                q = found[cid].reshape(4, 2)
                for i in range(4):                     # the marker's 4 sides
                    sides.append(float(np.linalg.norm(q[(i + 1) % 4] - q[i])))
            mean_side_px = sum(sides) / len(sides)
            raw_scale = self.corner_marker_cm / mean_side_px
            if self.last_scale is None:
                self.last_scale = raw_scale
            else:   # EMA smoothing: steadies the number, still tracks real
                    # changes (a bumped camera) within a few frames
                self.last_scale += self.SCALE_SMOOTH * (raw_scale - self.last_scale)
            scale = self.last_scale
            # marker-derived size (auto mode + cross-check for typed mode)
            self.auto_w = float(np.linalg.norm(centers[1] - centers[0])) * scale
            self.auto_h = float(np.linalg.norm(centers[3] - centers[0])) * scale
            # typed true size wins if provided (marker-CENTER distances!)
            self.width_cm = self.width_override or self.auto_w
            self.height_cm = self.height_override or self.auto_h
            dst = np.array([[0, 0], [self.width_cm, 0],
                            [self.width_cm, self.height_cm],
                            [0, self.height_cm]], dtype=np.float32)
            self.H = cv2.getPerspectiveTransform(centers, dst)
            self.last_good_H = self.H.copy()
        else:
            self.H = None

    @property
    def mode(self):
        if self.H is not None:
            return "corners"
        if self.last_good_H is not None:
            return "cached"
        return "scale"

    def _map(self, p):
        """One point through the homography (cm frame)."""
        pts = np.array([[p[0], p[1]]], dtype=np.float32).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(pts, self.last_good_H).reshape(2)
        return (float(out[0]), float(out[1]))

    def to_cm(self, p):
        """Pixel point -> (x, y) cm. (0,0) = the TL corner marker,
        x toward TR, y toward BL."""
        if self.last_good_H is not None:
            return self._map(p)
        s = self.last_scale if self.last_scale else self.cm_per_px
        return (float(p[0]) * s, float(p[1]) * s)

    def image_from_cm(self, pts_cm):
        """Map cm-frame points back into image pixels (for drawing)."""
        if self.last_good_H is None:
            return None
        h_inv = np.linalg.inv(self.last_good_H)
        pts = np.array(pts_cm, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, h_inv).reshape(-1, 2)

    def corner_sizes_cm(self, found):
        """Each corner marker's side length MAPPED into the cm frame.

        All four should read ~ the printed size (6 cm). A big spread means
        the taped quad is not a physical rectangle (or a corner moved) -
        and the mapping is warped, so distances read wrong per position."""
        if self.last_good_H is None:
            return None
        sizes = []
        for cid in CORNER_IDS:
            if cid not in found:
                return None
            q = found[cid].reshape(4, 2).astype(np.float32)
            cm = cv2.perspectiveTransform(
                q.reshape(-1, 1, 2), self.last_good_H).reshape(4, 2)
            s = np.mean([np.linalg.norm(cm[(i + 1) % 4] - cm[i])
                         for i in range(4)])
            sizes.append(float(s))
        return sizes

    def heading_cm(self, robot_corner):
        """Robot heading in the cm frame. The marker's front direction is
        mapped through the homography too, so a rotated/upscaled camera is
        corrected automatically. Fallback: raw image-frame yaw."""
        yaw_px = yaw_deg(robot_corner)
        if self.last_good_H is not None:
            c = center_of(robot_corner)
            a = math.radians(yaw_px)
            tip = np.array([c[0] + 80.0 * math.cos(a), c[1] + 80.0 * math.sin(a)])
            p0, p1 = self._map(c), self._map(tip)
            return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        return yaw_px


# =========================================================== navigation
class Navigator:
    """STEP-THEN-LOOK controller: move a little -> STOP -> look -> correct.

    (The kid's idea: acknowledge the feedback before every few steps.)
    Continuous streaming correction fought this hardware - loop latency,
    yaw jitter, and motors that only work in a narrow 25-40% PWM band.
    Instead every move is a short burst, then the robot STOPS and the next
    decision comes from a still, sharp image. Turn bursts self-calibrate:
    each burst measures how much the heading really changed, so the app
    learns the robot's true turn rate (deg/s) within a few bursts.
    """

    SETTLE_S = 0.35      # stopped time before measuring (motion blur dies)
    DRIVE_S = 0.7        # one straight burst
    TURN_MIN_S = 0.15
    TURN_MAX_S = 0.9
    HOLD_FRAMES = 3      # repeat last command this long when a marker drops
    RESUME_CM = 5.0      # arrived unlatches when the card moves this far out
    YAW_SMOOTH = 5
    RATE0 = 90.0         # initial turn-rate guess (deg/s)
    RATE_MIN, RATE_MAX = 25.0, 240.0
    TURN_FLOOR_PWM = 300 # ~29% - safely above the measured ~25% stall

    def __init__(self):
        self.speed = 400            # 0..1023, drive speed (slider)
        self.angle_tol = 25.0       # deg - re-aim if the error is past this
        self.stop_tol = 12.0        # cm - within this, arrived
        self.turn_invert = False    # flip turn direction if it turns AWAY
        self.heading_offset = 0.0   # deg - fixes a marker taped slightly off
        self.turn_rate = self.RATE0 # learned during the run
        self.reset()

    def reset(self):
        self.state = "IDLE"         # IDLE/SETTLE/TURNING/DRIVING/ARRIVED/LOST
        self.last_cmd = "S"
        self.miss = 0
        self.yaw_hist = deque(maxlen=self.YAW_SMOOTH)
        self.err_deg = 0.0
        self.dist_cm = 0.0
        self._heading_now = 0.0
        self._phase_t = 0.0         # seconds into the current phase
        self._slice_s = 0.0         # planned length of the current burst
        self._heading_before = None # heading at turn-burst start (rate learn)

    # ---- helpers ----
    def _smooth_heading(self, heading):
        self.yaw_hist.append(math.radians(heading))
        xs = [math.cos(a) for a in self.yaw_hist]
        ys = [math.sin(a) for a in self.yaw_hist]
        return math.degrees(math.atan2(sum(ys), sum(xs)))

    def _turn_cmd(self, err):
        c = "R" if err > 0 else "L"
        if self.turn_invert:
            c = "L" if c == "R" else "R"
        return c

    def _v_turn(self):
        """Constant burst speed: above stall, tame enough to stay sharp."""
        return max(self.TURN_FLOOR_PWM, min(500, self.speed))

    def _measure(self, robot_cm, heading_deg, target_cm):
        dx = target_cm[0] - robot_cm[0]
        dy = target_cm[1] - robot_cm[1]
        self.dist_cm = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dy, dx))
        self._heading_now = self._smooth_heading(heading_deg) + self.heading_offset
        self.err_deg = wrap180(bearing - self._heading_now)

    def _settle(self):
        self.state = "SETTLE"
        self._phase_t = 0.0
        self.yaw_hist.clear()          # next measurement = still frames only
        self.last_cmd = "S"

    def peek(self, robot_cm, heading_deg, target_cm):
        """Refresh the DISPLAYED dist/err without acting (robot not armed).
        Also powers the heading-offset calibration: aim the robot at the
        card by hand before START and read err straight off the screen."""
        self._measure(robot_cm, heading_deg, target_cm)

    # ---- the decision (call every UI tick; dt = seconds since last call) --
    def step(self, seen_robot, seen_target, robot_cm, heading_deg, target_cm,
             dt=0.03):

        # ---- marker dropout: hold briefly, then fail safe ----
        if not (seen_robot and seen_target):
            self.miss += 1
            if self.miss > self.HOLD_FRAMES:
                self.state = "LOST"
                self.last_cmd = "S"
            return self.last_cmd, self.speed
        self.miss = 0
        self._phase_t += dt

        # positions/errors refresh every frame (mid-burst stop checks)
        self._measure(robot_cm, heading_deg, target_cm)

        if self.state == "LOST":       # markers back - restart carefully
            self._settle()

        # ---- arrived: latch until the card is moved again ----
        if self.state == "ARRIVED":
            if self.dist_cm > self.stop_tol + self.RESUME_CM:
                self._settle()
            else:
                self.last_cmd = "S"
                return "S", self.speed
        if self.dist_cm <= self.stop_tol:
            self.state = "ARRIVED"
            self.last_cmd = "S"
            return "S", self.speed

        # ---- stopped: wait out the settle, then decide ONE burst ----
        if self.state in ("IDLE", "SETTLE"):
            self.last_cmd = "S"
            if self._phase_t < self.SETTLE_S:
                return "S", self.speed
            if abs(self.err_deg) >= self.angle_tol:
                dur = abs(self.err_deg) / self.turn_rate
                self._slice_s = min(max(dur, self.TURN_MIN_S), self.TURN_MAX_S)
                self._heading_before = self._heading_now
                self.state = "TURNING"
                self._phase_t = 0.0
                self.last_cmd = self._turn_cmd(self.err_deg)
                return self.last_cmd, self._v_turn()
            self._slice_s = self.DRIVE_S
            self.state = "DRIVING"
            self._phase_t = 0.0
            self.last_cmd = "F"
            return "F", self.speed

        # ---- turning burst ----
        if self.state == "TURNING":
            if self._phase_t >= self._slice_s:
                # learn the real turn rate from what actually happened
                if self._heading_before is not None and self._phase_t > 0.05:
                    dh = abs(wrap180(self._heading_now - self._heading_before))
                    measured = dh / self._phase_t
                    self.turn_rate = min(max(0.3 * measured
                                             + 0.7 * self.turn_rate,
                                             self.RATE_MIN), self.RATE_MAX)
                self._settle()
                return "S", self.speed
            self.last_cmd = self._turn_cmd(self.err_deg)
            return self.last_cmd, self._v_turn()

        # ---- driving burst ----
        if self._phase_t >= self._slice_s:
            self._settle()
            return "S", self.speed
        self.last_cmd = "F"
        return "F", self.speed


# =========================================================== overlay
def draw_overlay(frame, found, arena, nav):
    """Boxes + line + cm numbers + heading arrow, on one frame."""
    for cid in CORNER_IDS:
        if cid in found:
            pts = found[cid].reshape(4, 2).astype(int)
            cv2.polylines(frame, [pts], True, C_CORNER, 2)
            cv2.putText(frame, str(cid), (pts[0][0], pts[0][1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, C_CORNER, 2)

    # ---- arena geometry: raw taped quad vs the corrected cm rectangle ----
    if arena.last_good_H is not None:
        w_cm, h_cm = arena.width_cm, arena.height_cm
        rect = arena.image_from_cm([(0, 0), (w_cm, 0),
                                    (w_cm, h_cm), (0, h_cm)]).astype(int)
        cv2.polylines(frame, [rect], True, (60, 220, 60), 3)   # corrected
        centers = [center_of(found[cid]) for cid in CORNER_IDS if cid in found]
        if len(centers) == 4:
            cv2.polylines(frame, [np.array(centers, dtype=int)], True,
                          (255, 255, 255), 2)                  # as taped
        for gx in range(20, int(w_cm), 20):                     # 20 cm grid
            ln = arena.image_from_cm([(gx, 0), (gx, h_cm)]).astype(int)
            cv2.line(frame, tuple(ln[0]), tuple(ln[1]), (200, 200, 200), 1)
        for gy in range(20, int(h_cm), 20):
            ln = arena.image_from_cm([(0, gy), (w_cm, gy)]).astype(int)
            cv2.line(frame, tuple(ln[0]), tuple(ln[1]), (200, 200, 200), 1)

    for marker_id, color in ((ROBOT_ID, C_ROBOT), (TARGET_ID, C_TARGET)):
        if marker_id in found:
            pts = found[marker_id].reshape(4, 2).astype(int)
            cv2.polylines(frame, [pts], True, color, 3)
            cx, cy = center_of(found[marker_id])
            cv2.circle(frame, (int(cx), int(cy)), 6, color, -1)
            cv2.putText(frame, f"ID {marker_id}", (pts[0][0], pts[0][1] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    if ROBOT_ID in found and TARGET_ID in found:
        r, t = center_of(found[ROBOT_ID]), center_of(found[TARGET_ID])
        cv2.line(frame, r.astype(int), t.astype(int), C_LINE, 3)
        mid = (int((r[0] + t[0]) / 2), int((r[1] + t[1]) / 2))
        cv2.putText(frame, f"{nav.dist_cm:.0f} cm", (mid[0], mid[1] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, C_LINE, 2)
        # heading arrow in the image frame (what the camera sees)
        a = math.radians(yaw_deg(found[ROBOT_ID]))
        tip = (int(r[0] + 70 * math.cos(a)), int(r[1] + 70 * math.sin(a)))
        cv2.arrowedLine(frame, (int(r[0]), int(r[1])), tip, C_ARROW, 3, 4)
        cv2.putText(frame, f"err {nav.err_deg:+.0f} deg",
                    (int(r[0]) + 10, int(r[1]) - 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, C_ARROW, 2)


# =========================================================== the app
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

STATE_COLORS = {"IDLE": "#8a8a8a", "SETTLE": "#a0a0c0", "TURNING": "#e0a020",
                "DRIVING": "#20a0e0", "ARRIVED": "#30b030", "LOST": "#d04040"}


class VisionBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VisionBot - autonomous navigation")
        self.geometry("1280x780")

        self.detector = ArucoDetector()
        self.arena = ArenaMap()
        self.nav = Navigator()
        self.link = None            # created on START
        self.armed = False
        self.feed = None            # camera helper process (never None-blocking)
        self.cam_state = "off"      # off / opening / on
        self.cam_info = "camera off"
        self.photo = None
        self.fps, self.t_prev = 0.0, time.monotonic()
        self.last_send = 0.0
        self._v_sent = None         # last speed value pushed to the robot
        self._last_nav_t = 0.0      # for the dt the controller receives
        self._corner_sizes = None   # per-corner mapped size (taping health)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.bind("<space>", lambda e: self._start())
        self.bind("<Escape>", lambda e: self._estop())
        self.after(30, self._tick)

    # ------------------------------------------------ UI construction
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- top banner ---
        self.banner = ctk.CTkLabel(self, text="Press START (or SPACE)",
                                   font=ctk.CTkFont(size=26, weight="bold"),
                                   text_color="#eeeeee")
        self.banner.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        # --- video panel ---
        self.video = ctk.CTkLabel(self, text="")
        self.video.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)

        # --- right control panel ---
        panel = ctk.CTkFrame(self, width=340)
        panel.grid(row=0, column=1, rowspan=3, sticky="ns", padx=6, pady=8)
        panel.grid_propagate(False)

        def row_label(parent, text, r):
            ctk.CTkLabel(parent, text=text, anchor="w").grid(
                row=r, column=0, sticky="w", padx=12)
            lab = ctk.CTkLabel(parent, text="", anchor="e", width=60)
            lab.grid(row=r, column=1, sticky="e", padx=12)
            return lab

        r = 0
        ctk.CTkButton(panel, text="START  (SPACE)", height=44, fg_color="#2e8b2e",
                      command=self._start).grid(row=r, column=0, columnspan=2,
                                                sticky="ew", padx=12, pady=(12, 4))
        r += 1
        ctk.CTkButton(panel, text="PAUSE", height=36, fg_color="#b07020",
                      command=self._pause).grid(row=r, column=0, sticky="ew",
                                                padx=12, pady=4)
        ctk.CTkButton(panel, text="SNAPSHOT", height=36,
                      command=self._snapshot).grid(row=r, column=1,
                                                   sticky="ew", padx=12, pady=4)
        r += 1
        self.estop_btn = ctk.CTkButton(panel, text="E-STOP  (ESC)", height=56,
                                       fg_color="#c03030", hover_color="#e04040",
                                       font=ctk.CTkFont(size=18, weight="bold"),
                                       command=self._estop)
        self.estop_btn.grid(row=r, column=0, columnspan=2, sticky="ew",
                            padx=12, pady=(4, 10))
        r += 1
        self.speed_lab = row_label(panel, "Speed (constant)", r)
        self.speed = ctk.CTkSlider(panel, from_=25, to=100, number_of_steps=15,
                                   command=self._speed_changed)
        self.speed.set(35)
        self.speed.grid(row=r + 1, column=0, columnspan=2, sticky="ew",
                        padx=12, pady=(0, 8))
        self.speed_lab.configure(text="35%")
        r += 2
        self.angle_lab = row_label(panel, "Angle tolerance", r)
        self.angle = ctk.CTkSlider(panel, from_=10, to=45, number_of_steps=7,
                                   command=self._angle_changed)
        self.angle.set(25)
        self.angle.grid(row=r + 1, column=0, columnspan=2, sticky="ew",
                        padx=12, pady=(0, 8))
        self.angle_lab.configure(text="25 deg")
        r += 2
        self.stoptol_lab = row_label(panel, "Stop tolerance", r)
        self.stoptol = ctk.CTkSlider(panel, from_=5, to=20, number_of_steps=15,
                                     command=self._stoptol_changed)
        self.stoptol.set(12)
        self.stoptol.grid(row=r + 1, column=0, columnspan=2, sticky="ew",
                          padx=12, pady=(0, 8))
        self.stoptol_lab.configure(text="12 cm")
        r += 2
        self.invert = ctk.CTkCheckBox(
            panel, text="Invert turn direction",
            command=self._nav_params_changed)
        self.invert.grid(row=r, column=0, columnspan=2, sticky="w",
                         padx=12, pady=4)
        r += 1

        def entry_row(text, default, r):
            lab = ctk.CTkLabel(panel, text=text, anchor="w")
            lab.grid(row=r, column=0, sticky="w", padx=12)
            var = ctk.CTkEntry(panel, width=90, justify="center")
            var.insert(0, default)
            var.grid(row=r, column=1, sticky="e", padx=12)
            return var

        self.e_head = entry_row("Heading offset (deg)", "0", r); r += 1
        self.e_csize = entry_row("Corner marker (cm)", "6", r); r += 1
        self.e_w = entry_row("Frame W cm (empty=auto)", "", r); r += 1
        self.e_h = entry_row("Frame H cm (empty=auto)", "", r); r += 1
        self.e_scale = entry_row("cm/px (no corners)", "0.05", r); r += 1
        ctk.CTkButton(panel, text="Ruler check: card 30 cm from robot",
                      height=30, command=self._ruler_check).grid(
            row=r, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 4))
        r += 1
        self.e_cam = entry_row("Camera (empty=auto)", "", r); r += 1
        self.e_ip = entry_row("Robot IP", ROBOT_IP, r); r += 1

        ctk.CTkButton(panel, text="Start / Stop camera", height=34,
                      command=self._toggle_camera).grid(
            row=r, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))
        r += 1

        self.readout = ctk.CTkTextbox(panel, font=ctk.CTkFont(family="Courier New",
                                                              size=13))
        self.readout.grid(row=r, column=0, columnspan=2, sticky="ew",
                          padx=12, pady=(10, 12))
        self.readout.configure(height=210)

    # ------------------------------------------------ helpers
    def _f(self, entry, default):
        try:
            return float(entry.get())
        except (ValueError, TypeError):
            return default

    def _nav_params_changed(self):
        self.nav.angle_tol = float(self.angle.get())
        self.nav.stop_tol = float(self.stoptol.get())
        self.nav.turn_invert = bool(self.invert.get())
        self.nav.heading_offset = self._f(self.e_head, 0.0)

        def _opt(entry):                 # optional typed frame size, cm
            try:
                v = float(entry.get())
                return v if 20.0 <= v <= 400.0 else None
            except ValueError:
                return None

        self.arena.configure(self._f(self.e_csize, 6.0),
                             self._f(self.e_scale, 0.05),
                             _opt(self.e_w), _opt(self.e_h))

    def _speed_changed(self, value):
        pct = int(value)
        self.speed_lab.configure(text=f"{pct}%")
        self.nav.speed = pct * 1023 // 100
        if self.armed and self.link:
            self.link.send_speed(self.nav.speed)
            self._v_sent = self.nav.speed

    def _angle_changed(self, value):
        self.angle_lab.configure(text=f"{int(value)} deg")
        self._nav_params_changed()

    def _stoptol_changed(self, value):
        self.stoptol_lab.configure(text=f"{int(value)} cm")
        self._nav_params_changed()

    def _ruler_check(self):
        """One-press scale calibration: place the card EXACTLY 30 cm from
        the robot marker (ruler/tape, robot near the arena centre to
        minimise parallax), both visible on screen, then press. The corner
        marker size is corrected so the reading becomes exactly 30 cm."""
        d = self.nav.dist_cm
        if not (15.0 <= d <= 60.0):
            self.banner.configure(
                text="Ruler check: put the card 30 cm from the robot marker "
                     "(both visible), then press again",
                text_color="#e0a020")
            return
        old = self.arena.corner_marker_cm
        new = min(12.0, max(3.0, old * 30.0 / d))
        self.e_csize.delete(0, "end")
        self.e_csize.insert(0, f"{new:.1f}")
        self.arena.last_scale = None          # adopt the new scale instantly
        self._nav_params_changed()
        print(f"[calibrate] ruler check: read {d:.1f} cm for a true 30 cm -> "
              f"corner marker size {old:.1f} -> {new:.1f} cm")
        self.banner.configure(
            text=f"Scale calibrated: reads 30.0 cm now (marker size "
                 f"{old:.1f} -> {new:.1f} cm)",
            text_color="#30b030")

    # ------------------------------------------------ control actions
    def _start(self):
        if getattr(self.focus_get(), "widgetName", "") == "entry":
            return                                   # typing - don't hijack
        self._nav_params_changed()
        ip = self.e_ip.get().strip() or ROBOT_IP
        if self.link is None:
            self.link = RobotLink(ip, ROBOT_PORT)
        self.nav.reset()
        self.armed = True
        self._v_sent = self.nav.speed
        self.link.send_speed(self.nav.speed)
        print(f"[nav] START - target {ip}:{ROBOT_PORT}, "
              f"speed {self.nav.speed}/1023")

    def _pause(self):
        self.armed = False
        self.nav.state = "IDLE"
        if self.link:
            self.link.stop_burst()
        print("[nav] paused")

    def _estop(self):
        if getattr(self.focus_get(), "widgetName", "") == "entry":
            return
        self.armed = False
        self.nav.state = "IDLE"
        if self.link:
            self.link.stop_burst()
        print("[nav] E-STOP")

    def _snapshot(self):
        if self._last_frame is not None:
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            path = os.path.join(SNAPSHOT_DIR,
                                time.strftime("nav_%Y%m%d_%H%M%S.png"))
            cv2.imwrite(path, self._last_frame)
            print(f"snapshot saved: {path}")

    def _toggle_camera(self):
        if self.cam_state in ("on", "opening"):
            self.feed.shutdown()                 # graceful, force if wedged
            self.feed = None
            self.cam_state = "off"
            self.cam_info = "camera off"
            print("[camera] released")
            return
        indices = [0, 1, 2]                      # C920 was index 0 last time
        idx_text = self.e_cam.get().strip()
        if idx_text:
            try:
                indices = [int(idx_text)]
            except ValueError:
                pass
        self.feed = CameraFeed()
        self.cam_state = "opening"
        self.banner.configure(text="Opening camera... (runs in a helper "
                                   "process - this window stays responsive)",
                              text_color="#e0a020")
        print(f"[camera] opening: will try indices {indices}")
        self.feed.start_open(indices)

    def _on_cam_event(self, ev):
        """React to one status event from the camera helper."""
        kind = ev[0]
        if kind == "opening":
            self.banner.configure(text=f"Opening camera {ev[1]}... (a few seconds)",
                                  text_color="#e0a020")
        elif kind == "ok":
            _, idx, w, h = ev
            self.cam_state = "on"
            self.cam_info = f"camera {idx} ({w}x{h})"
            print(f"[camera] using {self.cam_info}")
        elif kind == "skip":
            print(f"[camera] index {ev[1]}: {ev[2]}px wide - not the C920, skipped")
        elif kind == "fail":
            self.cam_state = "off"
            self.banner.configure(
                text="No 1080p camera found - connect the Logitech C920, "
                     "then click Start/Stop camera",
                text_color="#d04040")
            print("[camera] no 1080p camera found - the demo needs the C920")
        elif kind == "stuck":
            self.feed.shutdown()
            self.cam_state = "off"
            self.banner.configure(
                text="Camera stuck (driver) - UNPLUG and REPLUG the C920, "
                     "then click Start/Stop camera",
                text_color="#d04040")
            print("[camera] helper went silent - killed. Unplug/replug the C920.")
        elif kind == "dead":
            self.cam_state = "off"
            self.banner.configure(
                text="Camera helper exited unexpectedly - click Start/Stop camera",
                text_color="#d04040")
            print(f"[camera] helper exitcode {ev[1]}")
        elif kind == "frameerr":
            print("[camera] frame stalled - if this repeats, toggle the camera off/on")

    # ------------------------------------------------ main loop
    _last_frame = None

    def _tick(self):
        now = time.monotonic()
        self.fps = 0.9 * self.fps + 0.1 / max(now - self.t_prev, 1e-6)
        self.t_prev = now
        cmd, v = None, None

        if self.feed is not None:
            for ev in self.feed.poll():
                self._on_cam_event(ev)
            frame = self.feed.latest_frame()
            if frame is not None:
                self._last_frame = frame
                found = self.detector.detect(frame)
                self.arena.update(found)
                self._corner_sizes = (self.arena.corner_sizes_cm(found)
                                      if self.arena.corner_error is None else None)
                if self.arena.corner_error:
                    self.banner.configure(
                        text="CORNER MARKERS mirrored/swapped! 30 must be "
                             "TOP-LEFT and 31 TOP-RIGHT as the camera sees. "
                             "Check the taping - using ruler fallback.",
                        text_color="#d04040")
                elif self._corner_sizes and \
                        max(self._corner_sizes) - min(self._corner_sizes) > 1.0:
                    self.banner.configure(
                        text="Corner taping not a true rectangle (marker sizes "
                             "read " + "/".join(f"{s:.1f}" for s in
                                                self._corner_sizes) +
                             " cm) - re-tape: equal DIAGONALS, then rerun the "
                             "30 cm check",
                        text_color="#e0a020")
                elif self.arena.width_override and self.arena.auto_w > 0 and \
                        abs(self.arena.auto_w / self.arena.width_override
                            - 1.0) > 0.15:
                    self.banner.configure(
                        text=f"Typed frame {self.arena.width_override:.0f}x"
                             f"{self.arena.height_override:.0f} differs a lot "
                             f"from marker-derived {self.arena.auto_w:.0f}x"
                             f"{self.arena.auto_h:.0f} - typed must be the "
                             "MARKER-CENTER distances of a true rectangle",
                        text_color="#e0a020")

                seen_r, seen_t = ROBOT_ID in found, TARGET_ID in found
                robot_cm = heading = target_cm = None
                if seen_r:
                    robot_cm = self.arena.to_cm(center_of(found[ROBOT_ID]))
                    heading = self.arena.heading_cm(found[ROBOT_ID])
                if seen_t:
                    target_cm = self.arena.to_cm(center_of(found[TARGET_ID]))

                if self.armed:
                    dt = max(0.001, now - self._last_nav_t)
                    self._last_nav_t = now
                    cmd, v = self.nav.step(seen_r, seen_t, robot_cm, heading,
                                           target_cm, dt=dt)
                elif seen_r and seen_t:
                    self.nav.peek(robot_cm, heading, target_cm)

                draw_overlay(frame, found, self.arena, self.nav)
                self._show(frame)

        self._update_readout(cmd)
        # send at SEND_HZ while armed (the keepalive feeds the robot deadman);
        # V goes out only when the desired speed actually changes
        if self.armed and self.link and cmd is not None and \
                now - self.last_send >= 1.0 / SEND_HZ:
            self.link.send(cmd)
            if v is not None and v != self._v_sent:
                self.link.send_speed(v)
                self._v_sent = v
            self.last_send = now

        self.after(30, self._tick)

    def _show(self, frame):
        target_w = 880
        scale = target_w / frame.shape[1]
        frame = cv2.resize(frame, (target_w, int(frame.shape[0] * scale)))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.video.configure(image=self.photo)

    def _update_readout(self, cmd):
        st = self.nav.state
        color = STATE_COLORS.get(st, "#8a8a8a")
        if self.cam_state == "opening":
            pass                                  # keep the "Opening..." banner
        elif self.cam_state == "off":
            self.banner.configure(
                text="Camera off - click 'Start / Stop camera'",
                text_color="#8a8a8a")
        else:
            text = {"IDLE": "Press START (or SPACE)",
                    "SETTLE": "LOOKING - stopped, measuring...",
                    "TURNING": f"TURNING   err {self.nav.err_deg:+.0f} deg",
                    "DRIVING": f"DRIVING   {self.nav.dist_cm:.0f} cm to card",
                    "ARRIVED": "ARRIVED - move the card to go again",
                    "LOST": "MARKER LOST - stopped (waiting to see both)"}.get(st, st)
            self.banner.configure(text=text, text_color=color)

        if self.arena.mode == "corners":
            if self.arena.width_override:
                arena_txt = (f"corners TYPED {self.arena.width_cm:.0f} x "
                             f"{self.arena.height_cm:.0f} cm "
                             f"(auto {self.arena.auto_w:.0f} x "
                             f"{self.arena.auto_h:.0f})")
            else:
                arena_txt = (f"corners (live)  W{self.arena.width_cm:.0f} x "
                             f"H{self.arena.height_cm:.0f} cm derived")
        elif self.arena.mode == "cached":
            arena_txt = "corners (cached homography)"
        elif self.arena.last_scale:
            arena_txt = "marker-derived scale (cached)"
        else:
            arena_txt = "RULER SCALE (no corners seen)"
        quad_txt = ("corner sizes " +
                    "/".join(f"{s:.1f}" for s in self._corner_sizes) + " cm"
                    if self._corner_sizes else
                    "green = corrected rectangle, white = as taped")
        lines = [
            f"state   : {st:<8} cmd {cmd or '-'}   speed {int(self.speed.get())}%",
            f"arena   : {arena_txt}",
            f"quad    : {quad_txt}",
            f"dist    : {self.nav.dist_cm:6.1f} cm   err {self.nav.err_deg:+6.1f} deg",
            f"tol     : {self.nav.angle_tol:.0f} deg / {self.nav.stop_tol:.0f} cm"
            f"   turn invert {'ON' if self.nav.turn_invert else 'off'}",
            f"radio   : {self.link.sent if self.link else 0} packets"
            f"   {self.cam_info}   {self.fps:.0f} fps",
        ]
        self.readout.delete("1.0", "end")
        self.readout.insert("1.0", "\n".join(lines))

    def _shutdown(self):
        self.armed = False
        if self.link:
            self.link.stop_burst()
            self.link.close()
        if self.feed is not None:
            self.feed.shutdown()
            self.feed = None
        self.destroy()


if __name__ == "__main__":
    VisionBotApp().mainloop()
