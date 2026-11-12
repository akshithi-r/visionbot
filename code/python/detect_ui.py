"""
VisionBot - ArUco detection test with a Gradio web UI

Same detection as detect_test.py, but shown in the browser:
  - live arena view: green box = robot (ID 10), blue box = target (ID 20),
    magenta line between them
  - big status badges showing whether each marker is detected
  - live numbers: positions, distance (px / cm), line angle, robot yaw, fps
  - settings: camera index, cm-per-pixel scale, 180-degree flip
  - snapshot button -> saves to snapshots/ and shows a gallery

Run (from the code/python folder):
  python detect_ui.py                       # camera 0, opens http://127.0.0.1:7860
  python detect_ui.py --cam 1 --scale 0.05 --flip

NOTE: only one program can use the webcam at a time - close the
detect_test.py window before starting this (and the other way round).
"""

import argparse
import os
import time

import cv2
import gradio as gr
import numpy as np

# reuse the detector and math from the command-line test - one source of truth
from detect_test import (ROBOT_ID, TARGET_ID, SNAPSHOT_DIR, ArucoDetector,
                         center_of, yaw_deg)

# colours in BGR (what OpenCV paints with)
C_ROBOT = (0, 220, 0)      # green
C_TARGET = (255, 120, 0)   # blue
C_LINE = (255, 0, 255)     # magenta

DETECTOR = ArucoDetector()
LATEST = {"rgb": None}          # last annotated frame (for snapshots)
LAST_SEEN = {}                  # {marker_id: time.time() of last detection}
CAM = {"cap": None, "index": None}


# ------------------------------------------------------------ camera
def open_camera(idx):
    """Open camera `idx`, reuse it if already open. Returns None on failure."""
    idx = int(idx)
    if CAM["cap"] is not None and CAM["index"] == idx:
        return CAM["cap"]
    if CAM["cap"] is not None:
        CAM["cap"].release()
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)      # faster open on Windows
    if not cap.isOpened():
        cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        CAM["cap"], CAM["index"] = None, None
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    try:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)          # stop focus hunting
    except Exception:
        pass
    CAM["cap"], CAM["index"] = cap, idx
    return cap


def message_frame(text):
    """Gray placeholder image with a message, for when the camera is closed."""
    img = np.full((480, 640, 3), 60, np.uint8)
    cv2.putText(img, text, (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


# ------------------------------------------------------------ drawing + status
def annotate(frame, found, scale):
    """Draw boxes/labels/line on one frame (BGR in, BGR out)."""
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
        mid = int((r[0] + t[0]) / 2), int((r[1] + t[1]) / 2 - 15)
        cv2.putText(frame, txt, mid, cv2.FONT_HERSHEY_SIMPLEX, 1.0, C_LINE, 2)
        cv2.putText(frame, f"line {line_deg:.0f} deg  yaw {yaw:.0f} deg",
                    (mid[0], mid[1] + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, C_LINE, 2)
        return {"dist_px": dist_px, "line_deg": line_deg, "yaw": yaw,
                "r": r, "t": t}
    return None


def badge(marker_id, name):
    """Green = seen right now, amber = brief dropout, red = gone / never seen."""
    now = time.time()
    seen_at = LAST_SEEN.get(marker_id)
    if seen_at is None:
        state = (f'&#10006; {name}: not seen yet', '#b3261e', '#fff')
    else:
        age = now - seen_at
        if age < 0.4:        # visible in (almost) the current frame
            state = (f'&#10004; {name}: detected', '#1f8f3b', '#fff')
        elif age < 2.0:      # dropped out a moment ago - probably a blur
            state = (f'&#9888; {name}: lost {age:.1f}s', '#e0a800', '#000')
        else:
            state = (f'&#10006; {name}: not seen for {age:.0f}s', '#b3261e', '#fff')
    text, bg, fg = state
    return (f'<span style="background:{bg};color:{fg};padding:6px 12px;'
            f'border-radius:18px;font-weight:bold">{text}</span>')


def status_html(now, seen_ids):
    both = ROBOT_ID in seen_ids and TARGET_ID in seen_ids
    banner = ('<div style="background:#1f8f3b;color:#fff;padding:10px;'
              'border-radius:10px;font-size:1.2em;font-weight:bold;text-align:center">'
              'BOTH MARKERS DETECTED - navigation possible</div>' if both else
              '<div style="background:#555;color:#fff;padding:10px;border-radius:10px;'
              'font-size:1.2em;font-weight:bold;text-align:center">'
              'waiting for both markers...</div>')
    gap = '<div style="height:8px"></div>'
    return (banner + gap + badge(ROBOT_ID, "ROBOT (ID 10)") + gap +
            badge(TARGET_ID, "TARGET (ID 20)"))


def readout_html(info, fps):
    rows = [f"fps: {fps:.0f}"]
    if info:
        r, t = info["r"], info["t"]
        rows += [f"robot : ({r[0]:.0f}, {r[1]:.0f}) px",
                 f"target: ({t[0]:.0f}, {t[1]:.0f}) px",
                 f"distance: {info['dist_px']:.0f} px",
                 f"line angle: {info['line_deg']:.1f} deg",
                 f"robot yaw: {info['yaw']:.1f} deg"]
    body = "<br>".join(rows)
    return (f'<div style="font-family:Consolas,monospace;font-size:1.05em;'
            f'background:#f5f5f5;padding:12px;border-radius:10px">{body}</div>')


# ------------------------------------------------------------ gradio callbacks
FPS = {"v": 0.0, "t": time.time()}


def tick(cam_idx, scale, flip):
    """Runs ~7x per second: grab frame, detect, annotate, update panels."""
    cam_idx = 0 if cam_idx is None else int(cam_idx)
    scale = float(scale) if scale else None
    now = time.time()
    FPS["v"] = 0.9 * FPS["v"] + 0.1 / max(now - FPS["t"], 1e-6)
    FPS["t"] = now

    cap = open_camera(cam_idx)
    if cap is None:
        img = message_frame("camera not open - try another camera index")
        return img, status_html(now, []), readout_html(None, FPS["v"])

    ok, frame = cap.read()                    # single read per tick
    if not ok:
        img = message_frame("camera stopped sending frames")
        return img, status_html(now, []), readout_html(None, FPS["v"])

    if flip:
        frame = cv2.rotate(frame, cv2.ROTATE_180)

    found = DETECTOR.detect(frame)
    for marker_id in found:
        LAST_SEEN[marker_id] = now

    info = annotate(frame, found, scale)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    LATEST["rgb"] = rgb
    return rgb, status_html(now, found), readout_html(info, FPS["v"])


SNAPS = []


def save_snapshot():
    if LATEST["rgb"] is None:
        return SNAPS, '<span style="color:#b3261e">no frame yet</span>'
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, time.strftime("snap_%Y%m%d_%H%M%S.png"))
    cv2.imwrite(path, cv2.cvtColor(LATEST["rgb"], cv2.COLOR_RGB2BGR))
    SNAPS.append(path)
    return SNAPS, f'<span style="color:#1f8f3b">saved: {os.path.basename(path)}</span>'


# ------------------------------------------------------------ ui layout
def build_demo(args):
    with gr.Blocks(title="VisionBot - Detection Test") as demo:
        gr.Markdown("# VisionBot - ArUco Detection Test\n"
                    "Green box = robot (ID 10) &bull; Blue box = destination card (ID 20) "
                    "&bull; Magenta line = robot &rarr; target")
        with gr.Row():
            with gr.Column(scale=3):
                image = gr.Image(interactive=False, label="Arena view",
                                 height=480)
            with gr.Column(scale=1):
                status = gr.HTML(value=status_html(time.time(), []))
                readout = gr.HTML(value=readout_html(None, 0))
                with gr.Accordion("Settings", open=True):
                    cam_in = gr.Number(value=args.cam, precision=0,
                                       label="Camera index")
                    scale_in = gr.Number(value=args.scale, precision=3,
                                         label="cm per pixel (Block 4 calibration)")
                    flip_in = gr.Checkbox(value=args.flip,
                                          label="Rotate image 180 degrees")
                snap_btn = gr.Button("Save snapshot (goes to snapshots/)")
                snap_info = gr.HTML()
                gallery = gr.Gallery(label="Snapshots", height=200)

        # refresh the view ~7x/second; Gradio 6 uses gr.Timer,
        # older versions take every= on demo.load - support both
        try:
            demo.load(tick, inputs=[cam_in, scale_in, flip_in],
                      outputs=[image, status, readout], every=0.15)
        except TypeError:
            gr.Timer(0.15).tick(tick, inputs=[cam_in, scale_in, flip_in],
                                outputs=[image, status, readout])
        snap_btn.click(save_snapshot, outputs=[gallery, snap_info])
    return demo


def main():
    ap = argparse.ArgumentParser(description="VisionBot detection test - Gradio UI")
    ap.add_argument("--cam", type=int, default=0, help="camera index (default 0)")
    ap.add_argument("--scale", type=float, default=None,
                    help="cm per pixel, e.g. 0.05")
    ap.add_argument("--flip", action="store_true",
                    help="rotate the image 180 degrees")
    args = ap.parse_args()

    demo = build_demo(args)
    demo.queue()
    demo.launch(inbrowser=True)          # opens http://127.0.0.1:7860 automatically


if __name__ == "__main__":
    main()
