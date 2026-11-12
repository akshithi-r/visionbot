# VisionBot on Ubuntu — Demo Machine Setup

The demo runs on an Ubuntu machine. The code auto-selects the right camera
backend per platform (DirectShow on Windows, V4L2 on Linux) — nothing to
change by hand. This page is everything else you need on the Ubuntu box.

## 1. One-time setup (~10 min)

```bash
sudo apt update
sudo apt install -y python3-venv libgl1 python3-tk   # libgl1 = opencv, python3-tk = Tkinter UI

cd robotproject/code/python                    # wherever the repo lives
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> No `libgl1` → `ImportError: libGL.so.1` when importing cv2. That error
> means exactly one thing: run the apt line above.

## 2. Camera check (before trusting the demo)

```bash
ls /dev/video*                       # C920 shows TWO nodes - video + metadata. Normal.
sudo apt install -y v4l-utils        # if v4l2-ctl is missing
v4l2-ctl --list-devices              # should list "HD Pro Webcam C920"
```

The UI's auto-detect probes the cameras and picks the one reporting
1920×1080 (the C920); the metadata node gives no frames and gets skipped
automatically.

If a camera opens for root but not the user:

```bash
groups | grep video || sudo usermod -aG video $USER   # then log out & back in
```

## 3. Run

```bash
source .venv/bin/activate
python detect_ui.py                  # auto-opens http://127.0.0.1:7860
```

Console narrates camera attempts: `[camera] index N: DSHOW ok` (Windows) or
the V4L2 equivalent — `opened camera N (1920x1080)` on success.

**Focus hunting on Ubuntu?** `CAP_PROP_AUTOFOCUS` may not stick via V4L2.
Fix from a terminal (C920 supports it):

```bash
v4l2-ctl -d /dev/video0 -c focus_auto=0
```

## 4. If re-flashing the NodeMCU from Ubuntu

USB serial needs dialout permission:

```bash
groups | grep dialout || sudo usermod -aG dialout $USER   # log out & back in
```

PlatformIO works the same otherwise (`nodemcuv2` board, unchanged).

## 5. Before the demo — the 2-minute acceptance test

Same as at home: 5 card spots (4 corners + center) all show green badges,
all four corner markers 30–33 visible at once, no amber flicker along the
far edge. **Run this on the Ubuntu machine itself, with the rig fully
assembled — not on the Windows laptop.**

## Platform notes for the curious (also in the code comments)

| Thing | Windows (dev laptop) | Ubuntu (demo) |
|---|---|---|
| Camera backend | DirectShow (`CAP_DSHOW`) — proven in Gradio threads | V4L2 (`CAP_V4L2`) — native, no COM quirks |
| Known trap | MSMF backend hangs in worker threads → never use | none |
| Open/read timeouts | honored by DSHOW | props ignored by V4L2 (harmless) |
| Python | `.venv\Scripts\python` | `.venv/bin/python` (`source .venv/bin/activate`) |
