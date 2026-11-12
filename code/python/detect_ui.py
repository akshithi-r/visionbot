"""
VisionBot - ArUco detection test, Tkinter + OpenCV (native, no browser)

A proper window with buttons and status panels, but 100% native:
Tkinter (comes with Python) + OpenCV. No Gradio, no server, no browser.

  - video: green box = robot (ID 10), blue box = target (ID 20),
    magenta line robot -> target with pixel/cm distance
  - banner turns green "BOTH MARKERS DETECTED" when both are visible
  - badges per marker: green = seen, amber = lost a moment, red = gone
  - buttons: Stop/Start camera, Save snapshot
  - settings: camera index (empty = auto-detect the 1080p webcam),
    cm per pixel, 180-degree flip - applied live, no restart
  - keys: s = snapshot, q / ESC = quit (same as the plain window)

Everything runs in the MAIN thread via root.after() - the camera + Tk
both like that, and it is the pattern proven to work on this laptop.
Close with q/ESC or the window X - both release the camera cleanly.

Run (from the code/python folder):
  python detect_ui.py                       # auto-detects the 1080p webcam
  python detect_ui.py --scale 0.05 --flip   # with calibration + flipped mount
  python detect_ui.py --cam 0               # force a specific camera index

The detection math and camera handling are imported from detect_test.py -
one source of truth for both windows.
"""

import argparse
import os
import time

import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk

from detect_test import (ROBOT_ID, TARGET_ID, SNAPSHOT_DIR, ArucoDetector,
                         annotate, drain_read, open_camera_auto,
                         open_camera_once)

DISPLAY_W = 960            # video width shown in the window

# badge colours (hex like CSS)
GREEN = "#1f8f3b"
AMBER = "#e0a800"
RED = "#b3261e"
GRAY = "#555555"


# ------------------------------------------------------------ pure helpers
def parse_int_or_none(value):
    """Camera index from the entry box: int, or None when empty/invalid."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_float_or_none(value):
    """Scale from the entry box: float, or None when empty/invalid."""
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def badge_state(seen_at, now):
    """(text, colour) for one marker badge, from its last-seen time."""
    if seen_at is None:
        return "not seen yet", RED
    age = now - seen_at
    if age < 0.4:
        return "detected", GREEN
    if age < 2.0:
        return f"lost {age:.1f}s", AMBER
    return f"not seen for {age:.0f}s", RED


def message_frame(text):
    """Gray placeholder image with a message, when the camera is closed."""
    img = np.full((540, 960, 3), 60, np.uint8)
    cv2.putText(img, text, (80, 270), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                (255, 255, 255), 2)
    return img


# ------------------------------------------------------------ the app
class VisionBotApp:
    def __init__(self, root, args):
        self.root = root
        self.args = args
        self.detector = ArucoDetector()

        self.cap = None            # open camera or None
        self.resolved = None       # what the cap belongs to: "auto" or int
        self.running = True        # Stop/Start button state
        self.next_open_attempt = 0.0   # rate-limit reopen retries
        self.last_seen = {}        # {marker_id: last-seen time}
        self.latest_rgb = None     # last annotated frame (for snapshots)
        self.fps, self.t_prev = 0.0, time.time()
        self.dbg_t = 0.0

        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("s", self.on_key)
        root.bind("q", self.on_key)
        root.bind("<Escape>", self.on_key)
        root.after(50, self.tick)

    # -------------------------------------------------- widgets
    def _build_ui(self):
        self.root.title("VisionBot - Detection Test")
        self.root.minsize(1300, 620)

        main = tk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # left: video
        left = tk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.video_label = tk.Label(left, bg="black",
                                    image=ImageTk.PhotoImage(
                                        Image.fromarray(message_frame("starting..."))))
        self.video_label.pack(fill=tk.BOTH, expand=True)

        # right: controls
        right = tk.Frame(main, width=330)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        self.banner = tk.Label(right, text="waiting for both markers...",
                               bg=GRAY, fg="white", wraplength=300,
                               font=("Segoe UI", 12, "bold"), pady=8)
        self.banner.pack(fill=tk.X, pady=(0, 8))

        self.badges = {}
        for mid, name in [(ROBOT_ID, "ROBOT (ID 10)"), (TARGET_ID, "TARGET (ID 20)")]:
            lab = tk.Label(right, text=f"{name}: not seen yet", bg=RED, fg="white",
                           font=("Segoe UI", 10, "bold"), pady=4, anchor="w",
                           padx=8)
            lab.pack(fill=tk.X, pady=2)
            self.badges[mid] = lab

        self.readout = tk.Label(right, text="ui fps: 0", anchor="nw",
                                justify=tk.LEFT, padx=8, pady=8,
                                font=("Consolas", 10), bg="#f5f5f5")
        self.readout.pack(fill=tk.X, pady=(8, 8))

        self.cam_btn = tk.Button(right, text="Stop camera",
                                 command=self.toggle_camera)
        self.cam_btn.pack(fill=tk.X, pady=2)
        tk.Button(right, text="Save snapshot (snapshots/)",
                  command=self.snapshot).pack(fill=tk.X, pady=2)

        box = tk.LabelFrame(right, text="Settings (live - no restart)")
        box.pack(fill=tk.X, pady=(10, 0))
        row = tk.Frame(box); row.pack(fill=tk.X, pady=3, padx=6)
        tk.Label(row, text="Camera index").pack(side=tk.LEFT)
        self.cam_entry = tk.Entry(row, width=8)
        self.cam_entry.insert(0, "" if self.args.cam is None else str(self.args.cam))
        self.cam_entry.pack(side=tk.LEFT, padx=6)
        tk.Label(row, text="(empty = auto 1080p)").pack(side=tk.LEFT)

        row2 = tk.Frame(box); row2.pack(fill=tk.X, pady=3, padx=6)
        tk.Label(row2, text="cm per pixel").pack(side=tk.LEFT)
        self.scale_entry = tk.Entry(row2, width=8)
        self.scale_entry.insert(0, "" if self.args.scale is None else str(self.args.scale))
        self.scale_entry.pack(side=tk.LEFT, padx=6)

        self.flip_var = tk.BooleanVar(value=self.args.flip)
        tk.Checkbutton(box, text="Rotate image 180 degrees",
                       variable=self.flip_var).pack(anchor="w", padx=6, pady=3)

        self.statusbar = tk.Label(self.root, anchor="w", fg="#444444",
                                  text="keys: s = snapshot, q / ESC = quit")
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

    # -------------------------------------------------- camera
    def ensure_camera(self, now):
        """Release/reopen so the open camera matches what the user asked
        for. All in the main thread - the proven-safe place for cameras."""
        if not self.running:
            self._release()
            return None
        want = parse_int_or_none(self.cam_entry.get())
        want = "auto" if want is None else want

        if self.cap is not None and self.resolved == want:
            return self.cap
        self._release()
        if now < self.next_open_attempt:      # don't hammer a dead camera
            return None
        self.next_open_attempt = now + 2.0

        if want == "auto":
            print("[camera] auto-detecting (looking for the 1080p webcam)...")
            cap = open_camera_auto()
        else:
            cap = open_camera_once(int(want))
        if cap is not None:
            self.cap, self.resolved = cap, want
        return self.cap

    def _release(self):
        if self.cap is not None:
            self.cap.release()                # clean release - never skip
        self.cap, self.resolved = None, None

    # -------------------------------------------------- main loop (main thread)
    def tick(self):
        now = time.time()
        self.fps = 0.9 * self.fps + 0.1 / max(now - self.t_prev, 1e-6)
        self.t_prev = now
        scale = parse_float_or_none(self.scale_entry.get())

        cap = self.ensure_camera(now)
        frame = drain_read(cap) if cap is not None else None

        if frame is None:
            text = ("camera stopped - press Start camera"
                    if not self.running else "no camera - check connection")
            display = message_frame(text)
            info, found = None, {}
        else:
            if self.flip_var.get():
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            found = self.detector.detect(frame)
            for mid in found:
                self.last_seen[mid] = now
            info = annotate(frame, found, scale)
            self.latest_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            if w > DISPLAY_W:
                frame = cv2.resize(frame, (DISPLAY_W, int(h * DISPLAY_W / w)))
            display = frame
            if now - self.dbg_t > 3:
                self.dbg_t = now
                print(f"[frame] {w}x{h} mean brightness="
                      f"{frame.mean():.0f} fps={self.fps:.0f}")

        # show the picture
        img = Image.fromarray(cv2.cvtColor(display, cv2.COLOR_BGR2RGB))
        self._tkimg = ImageTk.PhotoImage(img)     # keep a reference (GC!)
        self.video_label.config(image=self._tkimg)

        # banner + badges + readout
        both = ROBOT_ID in found and TARGET_ID in found
        self.banner.config(text="BOTH MARKERS DETECTED" if both
                           else "waiting for both markers...",
                           bg=GREEN if both else GRAY)
        for mid, name in [(ROBOT_ID, "ROBOT (ID 10)"), (TARGET_ID, "TARGET (ID 20)")]:
            text, colour = badge_state(self.last_seen.get(mid), now)
            self.badges[mid].config(text=f"{name}: {text}", bg=colour)

        cam_info = (f"camera: index {self.resolved} ({self.cap.get(cv2.CAP_PROP_FRAME_WIDTH):.0f}x"
                    f"{self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT):.0f})"
                    if self.cap is not None else "camera: none")
        lines = [f"ui fps: {self.fps:.0f}", cam_info]
        if info:
            r, t = info["r"], info["t"]
            lines += [f"robot : ({r[0]:.0f}, {r[1]:.0f}) px",
                      f"target: ({t[0]:.0f}, {t[1]:.0f}) px",
                      f"distance: {info['dist_px']:.0f} px"
                      + (f" = {info['dist_px'] * scale:.1f} cm" if scale else ""),
                      f"line angle: {info['line_deg']:.1f} deg",
                      f"robot yaw: {info['yaw']:.1f} deg"]
        self.readout.config(text="\n".join(lines))

        self.root.after(30, self.tick)            # ~30 ms loop, main thread

    # -------------------------------------------------- actions
    def toggle_camera(self):
        if self.running:
            self.running = False
            self._release()
            self.cam_btn.config(text="Start camera")
        else:
            self.running = True
            self.cam_btn.config(text="Stop camera")

    def snapshot(self):
        if self.latest_rgb is None:
            return
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        path = os.path.join(SNAPSHOT_DIR, time.strftime("snap_%Y%m%d_%H%M%S.png"))
        cv2.imwrite(path, cv2.cvtColor(self.latest_rgb, cv2.COLOR_RGB2BGR))
        self.statusbar.config(text=f"snapshot saved: {path}")

    def on_key(self, event):
        if isinstance(self.root.focus_get(), tk.Entry):
            return                                # typing in a box - ignore
        if event.keysym in ("q", "Escape"):
            self.close()
        elif event.keysym == "s":
            self.snapshot()

    def close(self):
        self._release()                           # clean camera release
        self.root.destroy()


def main():
    ap = argparse.ArgumentParser(description="VisionBot detection test - Tkinter UI")
    ap.add_argument("--cam", type=int, default=None,
                    help="camera index; omit to auto-detect the 1080p webcam")
    ap.add_argument("--scale", type=float, default=None,
                    help="cm per pixel, e.g. 0.05")
    ap.add_argument("--flip", action="store_true",
                    help="rotate the image 180 degrees")
    args = ap.parse_args()

    root = tk.Tk()
    VisionBotApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
