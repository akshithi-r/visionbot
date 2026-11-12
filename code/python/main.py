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

Camera rule on this project: main-thread only, DSHOW (Windows) / V4L2 (Ubuntu),
auto-detect the 1080p C920 - same proven pattern as detect_test.py.

Run:  .venv\\Scripts\\python main.py        (Windows)
      .venv/bin/python main.py             (Ubuntu demo box)
Robot Wi-Fi "VisionBot" joined first, robot powered, camera rig up.
"""

import math
import os
import socket
import sys
import time
from collections import deque

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_test import (ArucoDetector, center_of, yaw_deg,
                         open_camera_once, open_camera_auto, drain_read,
                         ROBOT_ID, TARGET_ID, SNAPSHOT_DIR)

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


# =========================================================== arena mapping
class ArenaMap:
    """Pixel -> true-cm mapping from the four taped corner markers.

    All four corners visible -> homography recomputed THIS frame (a bumped
    camera at the venue heals itself). Robot covering one corner -> use the
    cached last-good homography. No corners at all -> single ruler scale.
    """

    def __init__(self, width_cm=100.0, height_cm=70.0, cm_per_px=0.05):
        self.width_cm = float(width_cm)
        self.height_cm = float(height_cm)
        self.cm_per_px = float(cm_per_px)
        self.H = None            # live homography this frame
        self.last_good_H = None  # cache while a corner is hidden

    def configure(self, width_cm, height_cm, cm_per_px):
        self.width_cm = float(width_cm)
        self.height_cm = float(height_cm)
        self.cm_per_px = float(cm_per_px)

    def update(self, found):
        """Call once per frame with all detected markers."""
        if all(cid in found for cid in CORNER_IDS):
            src = np.array([center_of(found[cid]) for cid in CORNER_IDS],
                           dtype=np.float32)
            w, h = self.width_cm, self.height_cm
            dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
            self.H = cv2.getPerspectiveTransform(src, dst)
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
        return (float(p[0]) * self.cm_per_px, float(p[1]) * self.cm_per_px)

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
    """The decision box: turn in place -> drive straight -> stop.
    Pure logic, no camera/UI - kept testable on its own."""

    HOLD_FRAMES = 3      # repeat last command this long when a marker drops
    RESUME_CM = 5.0      # arrived unlatches when the card moves this far out

    def __init__(self):
        self.speed = 400            # 0..1023, the ONE constant speed
        self.angle_tol = 20.0       # deg - within this, drive straight
        self.stop_tol = 10.0        # cm - within this, arrived
        self.turn_invert = False    # flip if the robot turns AWAY from the card
        self.heading_offset = 0.0   # deg - fixes a marker taped slightly off
        self.reset()

    def reset(self):
        self.state = "IDLE"         # IDLE / TURNING / DRIVING / ARRIVED / LOST
        self.last_cmd = "S"
        self.miss = 0
        self.yaw_hist = deque(maxlen=5)   # yaw smoothing (heading is jittery)
        self.err_deg = 0.0
        self.dist_cm = 0.0

    def _smooth_heading(self, heading):
        self.yaw_hist.append(math.radians(heading))
        xs = [math.cos(a) for a in self.yaw_hist]
        ys = [math.sin(a) for a in self.yaw_hist]
        return math.degrees(math.atan2(sum(ys), sum(xs)))

    def step(self, seen_robot, seen_target, robot_cm, heading_deg, target_cm):
        """One decision. Returns the command char to send."""
        # ---- marker dropout: hold briefly, then fail safe ----
        if not (seen_robot and seen_target):
            self.miss += 1
            if self.miss > self.HOLD_FRAMES:
                self.state = "LOST"
                self.last_cmd = "S"
            return self.last_cmd          # hold within the grace window

        self.miss = 0
        dx = target_cm[0] - robot_cm[0]
        dy = target_cm[1] - robot_cm[1]
        self.dist_cm = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dy, dx))
        heading = self._smooth_heading(heading_deg) + self.heading_offset
        self.err_deg = wrap180(bearing - heading)

        # ---- arrived: latch until the card is moved again ----
        if self.state == "ARRIVED":
            if self.dist_cm > self.stop_tol + self.RESUME_CM:
                self.state = "TURNING"    # card moved - re-aim
            else:
                self.last_cmd = "S"
                return self.last_cmd
        elif self.dist_cm <= self.stop_tol:
            self.state = "ARRIVED"
            self.last_cmd = "S"
            return self.last_cmd

        # ---- turn or drive ----
        if abs(self.err_deg) > self.angle_tol:
            cmd = "R" if self.err_deg > 0 else "L"
            if self.turn_invert:
                cmd = "L" if cmd == "R" else "R"
            self.state = "TURNING"
        else:
            cmd = "F"
            self.state = "DRIVING"
        self.last_cmd = cmd
        return cmd


# =========================================================== overlay
def draw_overlay(frame, found, arena, nav):
    """Boxes + line + cm numbers + heading arrow, on one frame."""
    for cid in CORNER_IDS:
        if cid in found:
            pts = found[cid].reshape(4, 2).astype(int)
            cv2.polylines(frame, [pts], True, C_CORNER, 2)
            cv2.putText(frame, str(cid), (pts[0][0], pts[0][1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, C_CORNER, 2)

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

STATE_COLORS = {"IDLE": "#8a8a8a", "TURNING": "#e0a020", "DRIVING": "#20a0e0",
                "ARRIVED": "#30b030", "LOST": "#d04040"}


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
        self.cap = None
        self.cam_info = "camera off"
        self.photo = None
        self.fps, self.t_prev = 0.0, time.monotonic()
        self.last_send = 0.0

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
        self.speed = ctk.CTkSlider(panel, from_=10, to=100, number_of_steps=18,
                                   command=self._speed_changed)
        self.speed.set(40)
        self.speed.grid(row=r + 1, column=0, columnspan=2, sticky="ew",
                        padx=12, pady=(0, 8))
        self.speed_lab.configure(text="40%")
        r += 2
        self.angle_lab = row_label(panel, "Angle tolerance", r)
        self.angle = ctk.CTkSlider(panel, from_=10, to=45, number_of_steps=7,
                                   command=self._angle_changed)
        self.angle.set(20)
        self.angle.grid(row=r + 1, column=0, columnspan=2, sticky="ew",
                        padx=12, pady=(0, 8))
        self.angle_lab.configure(text="20 deg")
        r += 2
        self.stoptol_lab = row_label(panel, "Stop tolerance", r)
        self.stoptol = ctk.CTkSlider(panel, from_=5, to=20, number_of_steps=15,
                                     command=self._stoptol_changed)
        self.stoptol.set(10)
        self.stoptol.grid(row=r + 1, column=0, columnspan=2, sticky="ew",
                          padx=12, pady=(0, 8))
        self.stoptol_lab.configure(text="10 cm")
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
        self.e_w = entry_row("Arena width (cm)", "100", r); r += 1
        self.e_h = entry_row("Arena height (cm)", "70", r); r += 1
        self.e_scale = entry_row("cm/px (no corners)", "0.05", r); r += 1
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
        self.arena.configure(self._f(self.e_w, 100.0), self._f(self.e_h, 70.0),
                             self._f(self.e_scale, 0.05))

    def _speed_changed(self, value):
        pct = int(value)
        self.speed_lab.configure(text=f"{pct}%")
        self.nav.speed = pct * 1023 // 100
        if self.armed and self.link:
            self.link.send_speed(self.nav.speed)

    def _angle_changed(self, value):
        self.angle_lab.configure(text=f"{int(value)} deg")
        self._nav_params_changed()

    def _stoptol_changed(self, value):
        self.stoptol_lab.configure(text=f"{int(value)} cm")
        self._nav_params_changed()

    # ------------------------------------------------ control actions
    def _start(self):
        if isinstance(self.focus_get(), type(self.e_w)) or \
                getattr(self.focus_get(), "widgetName", "") == "entry":
            return                                   # typing - don't hijack
        self._nav_params_changed()
        ip = self.e_ip.get().strip() or ROBOT_IP
        if self.link is None:
            self.link = RobotLink(ip, ROBOT_PORT)
        self.nav.reset()
        self.armed = True
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
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            self.cam_info = "camera off"
            print("[camera] released")
            return
        idx_text = self.e_cam.get().strip()
        if idx_text:
            self.cap = open_camera_once(int(idx_text))
        else:
            print("[camera] auto-detecting (looking for the 1080p webcam)...")
            self.cap = open_camera_auto()
        if self.cap is not None:
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.cam_info = f"camera ({w}x{h})"

    # ------------------------------------------------ main loop
    _last_frame = None

    def _tick(self):
        now = time.monotonic()
        self.fps = 0.9 * self.fps + 0.1 / max(now - self.t_prev, 1e-6)
        self.t_prev = now
        cmd = None

        if self.cap is not None:
            frame = drain_read(self.cap)
            if frame is not None:
                self._last_frame = frame
                found = self.detector.detect(frame)
                self.arena.update(found)

                seen_r, seen_t = ROBOT_ID in found, TARGET_ID in found
                robot_cm = heading = target_cm = None
                if seen_r:
                    robot_cm = self.arena.to_cm(center_of(found[ROBOT_ID]))
                    heading = self.arena.heading_cm(found[ROBOT_ID])
                if seen_t:
                    target_cm = self.arena.to_cm(center_of(found[TARGET_ID]))

                if self.armed:
                    cmd = self.nav.step(seen_r, seen_t, robot_cm, heading,
                                        target_cm)

                draw_overlay(frame, found, self.arena, self.nav)
                self._show(frame)

        self._update_readout(cmd)
        # send at SEND_HZ while armed (the keepalive feeds the robot deadman)
        if self.armed and self.link and cmd is not None and \
                now - self.last_send >= 1.0 / SEND_HZ:
            self.link.send(cmd)
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
        text = {"IDLE": "Press START (or SPACE)",
                "TURNING": f"TURNING   err {self.nav.err_deg:+.0f} deg",
                "DRIVING": f"DRIVING   {self.nav.dist_cm:.0f} cm to card",
                "ARRIVED": "ARRIVED - move the card to go again",
                "LOST": "MARKER LOST - stopped (waiting to see both)"}.get(st, st)
        self.banner.configure(text=text, text_color=color)

        mode = {"corners": "corner markers (live)",
                "cached": "corner markers (cached)",
                "scale": "RULER SCALE (no corners seen)"}
        lines = [
            f"state   : {st:<8} cmd {cmd or '-'}   speed {int(self.speed.get())}%",
            f"arena   : {mode[self.arena.mode]}",
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
        if self.cap is not None:
            self.cap.release()
        self.destroy()


if __name__ == "__main__":
    VisionBotApp().mainloop()
