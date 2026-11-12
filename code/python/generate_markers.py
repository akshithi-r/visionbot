"""
VisionBot - ArUco marker generator (+ A4 print PDF)

Creates the two printable markers:
  ID 10 -> glued on top of the robot
  ID 20 -> on the destination card

Dictionary: DICT_4X4_50 (small pattern = fast, reliable detection at our
camera distance). Any of the 50 IDs in this dictionary would work; we use
10 and 20 because the proposal says so.

Run (from the code/python folder):
  python generate_markers.py

Output (in the markers/ folder next to this file):
  marker_10_robot.png    pure marker squares
  marker_20_target.png
  print_10_robot.png     full print sheets with FRONT arrow + instructions
  print_20_target.png
  print_a4_markers.pdf   BOTH markers, one per A4 page (easiest to print)
                         + page 3: four ARENA CORNER markers (IDs 30-33)

Printing: print the PDF at 100% scale ("Actual size", NOT "fit to page").
The black square must measure 8 x 8 cm. Matte paper if possible. Glue
FLAT - a bent marker is hard to detect.
"""

import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROBOT_ID = 10
TARGET_ID = 20
# Arena corner markers, named as the CAMERA sees the picture. They are the
# fixed reference points the navigation uses to correct a tilted/angled
# camera (perspective). Different IDs so they can never be confused with
# the robot (10) or the target card (20).
CORNER_IDS = {"TL": 30, "TR": 31, "BR": 32, "BL": 33}
CORNER_BLACK_PX = 709            # ~6 cm at 300 dpi - corners stay smaller
SIDE_PX = 800          # 800 px printed at 8 cm = ~250 dpi, nicely sharp
SHEET_W = 1200         # width of the print sheet
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "markers")

# --- A4 PDF layout (all at 300 dpi) --------------------------------------
DPI = 300
A4_W, A4_H = 2480, 3508             # 210 x 297 mm
BLACK_PX = 945                      # 945 px / 300 dpi = 8.00 cm black square
QUIET_PX = BLACK_PX // 8            # white quiet border, ~1 cm
CUT_MARGIN = int(0.5 / 2.54 * DPI)  # extra white kept when cutting, ~0.5 cm
FONT_DIR = r"C:\Windows\Fonts"


def _font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except OSError:
        return ImageFont.load_default(size=size)


def dictionary():
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def make_marker(marker_id, side_px=SIDE_PX):
    """Black-and-white marker with a white quiet border around it.

    Detection NEEDS white space around the black square - without it the
    marker is invisible to the detector. The border is 1/8 of the side.
    """
    if hasattr(cv2.aruco, "generateImageMarker"):        # OpenCV 4.7+
        raw = cv2.aruco.generateImageMarker(dictionary(), marker_id, side_px)
    else:                                                # older API
        raw = cv2.aruco.drawMarker(dictionary(), marker_id, side_px)
    pad = side_px // 8
    return cv2.copyMakeBorder(raw, pad, pad, pad, pad,
                              cv2.BORDER_CONSTANT, value=255)


def draw_arrow_up(img, center_x, top_y):
    """Small black arrow - shows which edge of the marker faces the FRONT."""
    size = 36
    triangle = np.array([[center_x, top_y],
                         [center_x - size, top_y + size],
                         [center_x + size, top_y + size]], np.int32)
    cv2.fillPoly(img, [triangle], (0, 0, 0))
    cv2.rectangle(img, (center_x - 5, top_y + size),
                  (center_x + 5, top_y + size + 45), (0, 0, 0), -1)
    cv2.putText(img, "FRONT", (center_x - 70, top_y + size + 90),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 3)


def make_sheet(marker, marker_id, who):
    """Print sheet: title, FRONT arrow, marker, cutting note."""
    m = marker.shape[0]                         # marker size incl. white border
    top = 230                                   # space for title + arrow
    sheet = np.full((top + m + 140, SHEET_W, 3), 255, np.uint8)
    cv2.putText(sheet, f"VisionBot - ID {marker_id} - {who}", (30, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    cv2.putText(sheet, "print at 100% (Actual size)  |  black square = 8 x 8 cm",
                (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 80), 2)
    cv2.putText(sheet, "arrow shows which edge points to the FRONT of the robot"
                if marker_id == ROBOT_ID else "destination card - arrow edge is 'up', any facing is fine",
                (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 2)

    draw_arrow_up(sheet, SHEET_W // 2, 175)

    x0 = (SHEET_W - m) // 2
    sheet[top:top + m, x0:x0 + m] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    cv2.rectangle(sheet, (x0 - 2, top - 2), (x0 + m + 1, top + m + 1),
                  (120, 120, 120), 2)          # cutting guide
    cv2.putText(sheet, "cut on the gray line, glue flat", (30, top + m + 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 80, 80), 2)
    return sheet


def make_a4_page(marker, marker_id, who, is_robot):
    """One A4 portrait page: title, arrow, 8 cm marker, check bar, steps."""
    img = Image.new("L", (A4_W, A4_H), 255)
    d = ImageDraw.Draw(img)
    f_title = _font("arialbd.ttf", 96)
    f_sub = _font("arial.ttf", 60)
    f_step = _font("arial.ttf", 52)
    f_tiny = _font("arial.ttf", 42)
    cx = A4_W // 2

    d.text((cx, 150), f"VisionBot  -  ID {marker_id}  -  {who}",
           font=f_title, fill=0, anchor="ma")
    d.text((cx, 250), 'Print at 100% ("Actual size") on A4 - NOT "fit to page"',
           font=f_sub, fill=90, anchor="ma")

    # FRONT arrow above the marker
    top_y, size = 330, 46
    d.polygon([(cx, top_y), (cx - size, top_y + size), (cx + size, top_y + size)],
              fill=0)
    d.rectangle([cx - 8, top_y + size, cx + 8, top_y + size + 70], fill=0)
    label = ("FRONT - this edge points to the FRONT of the robot" if is_robot
             else "card edge 'up' (any facing is fine)")
    d.text((cx, top_y + size + 160), label, font=f_step, fill=0, anchor="ma")

    # marker block with quiet border, gray cutting line OUTSIDE the border
    block = QUIET_PX * 2 + BLACK_PX
    top = 700
    img.paste(Image.fromarray(marker), (cx - block // 2, top))
    x0, y0 = cx - block // 2 - CUT_MARGIN, top - CUT_MARGIN
    x1, y1 = cx + block // 2 + CUT_MARGIN, top + block + CUT_MARGIN
    d.rectangle([x0, y0, x1, y1], outline=140, width=4)
    d.text((cx, y1 + 70),
           "cut on the GRAY line - KEEP the white border around the black square",
           font=f_step, fill=90, anchor="ma")

    # 8 cm check bar with one tick per centimetre
    bar_y = y1 + 160
    d.rectangle([cx - BLACK_PX // 2, bar_y, cx + BLACK_PX // 2, bar_y + 36], fill=0)
    for i in range(1, 8):
        x = cx - BLACK_PX // 2 + round(i * BLACK_PX / 8)
        d.line([(x, bar_y + 6), (x, bar_y + 30)], fill=255, width=4)
    d.text((cx, bar_y + 100),
           "check bar: must measure exactly 8.0 cm (8 ticks = 8 cm)",
           font=f_step, fill=0, anchor="ma")

    common = ["Print at 100% / 'Actual size' on A4 - no 'fit to page', no shrinking.",
              "Measure the black square: should be ~8.0 x 8.0 cm - note the real size.",
              "Cut on the gray line, KEEPING the white border (the camera needs it)."]
    steps = common + (["Glue FLAT on thin cardboard, fix it level on top of the robot.",
                       "FRONT arrow must point towards the robot's front (travel direction)."]
                      if is_robot else
                      ["Glue FLAT in the middle of a ~12 x 12 cm card (destination card).",
                       "Any orientation is fine - the robot reaches the card from any side."])
    y = bar_y + 210
    for i, s in enumerate(steps, 1):
        d.text((cx - 1050, y), f"{i}.  {s}", font=f_step, fill=0)
        y += 90

    d.text((cx, A4_H - 100),
           f"VisionBot science exhibition - ArUco DICT_4X4_50, marker ID {marker_id}",
           font=f_tiny, fill=140, anchor="ma")
    return img


def make_corner_page():
    """One A4 page with the four arena corner markers in a 2 x 2 grid."""
    img = Image.new("L", (A4_W, A4_H), 255)
    d = ImageDraw.Draw(img)
    f_title = _font("arialbd.ttf", 84)
    f_sub = _font("arial.ttf", 54)
    f_label = _font("arialbd.ttf", 56)
    f_tiny = _font("arial.ttf", 42)
    cx = A4_W // 2

    d.text((cx, 140), "VisionBot - ARENA CORNER MARKERS (IDs 30-33)",
           font=f_title, fill=0, anchor="ma")
    d.text((cx, 240), "These let the program correct an angled/tilted camera automatically.",
           font=f_sub, fill=90, anchor="ma")
    d.text((cx, 320), "Tape each one FLAT inside its arena corner, named as the CAMERA sees the picture:",
           font=f_sub, fill=90, anchor="ma")

    block = CORNER_BLACK_PX + 2 * (CORNER_BLACK_PX // 8)   # with quiet border
    cell_w, cell_h = 1150, 1160
    grid_x0 = (A4_W - 2 * cell_w) // 2
    grid_y0 = 440
    # reading order on the page: TL, TR / BL, BR
    cells = [("TL", "ID 30 - TOP-LEFT corner"), ("TR", "ID 31 - TOP-RIGHT corner"),
             ("BL", "ID 33 - BOTTOM-LEFT corner"), ("BR", "ID 32 - BOTTOM-RIGHT corner")]
    for i, (corner, name) in enumerate(cells):
        r, c = divmod(i, 2)
        x0 = grid_x0 + c * cell_w
        y0 = grid_y0 + r * cell_h
        marker = make_marker(CORNER_IDS[corner], CORNER_BLACK_PX)
        img.paste(Image.fromarray(marker), (x0 + (cell_w - block) // 2, y0))
        d.rectangle([x0 + (cell_w - block) // 2 - CUT_MARGIN, y0 - CUT_MARGIN,
                     x0 + (cell_w + block) // 2 + CUT_MARGIN, y0 + block + CUT_MARGIN],
                    outline=140, width=4)
        d.text((x0 + cell_w // 2, y0 + block + CUT_MARGIN + 70), name,
               font=f_label, fill=0, anchor="ma")

    y = grid_y0 + 2 * cell_h + 60
    d.text((cx, y), "Each corner marker is ~6 x 6 cm and stays fixed for the whole demo.",
           font=f_sub, fill=90, anchor="ma")
    d.text((cx, y + 80), "Check on screen: a robot standing near ID 30 must appear at the TOP-LEFT of the picture.",
           font=f_sub, fill=90, anchor="ma")
    d.text((cx, y + 160), "If corners end up swapped on the arena, the robot will drive mirrored - just re-tape.",
           font=f_sub, fill=90, anchor="ma")
    d.text((cx, A4_H - 100),
           "VisionBot science exhibition - ArUco DICT_4X4_50, corner markers",
           font=f_tiny, fill=140, anchor="ma")
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    jobs = [(ROBOT_ID, "ROBOT (top of robot)", True),
            (TARGET_ID, "TARGET (destination card)", False)]

    pdf_pages = []
    for marker_id, who, is_robot in jobs:
        name = "robot" if is_robot else "target"
        marker = make_marker(marker_id)
        pure_path = os.path.join(OUT_DIR, f"marker_{marker_id}_{name}.png")
        sheet_path = os.path.join(OUT_DIR, f"print_{marker_id}_{name}.png")
        cv2.imwrite(pure_path, marker)
        cv2.imwrite(sheet_path, make_sheet(marker, marker_id, who))
        pdf_pages.append(make_a4_page(make_marker(marker_id, BLACK_PX),
                                      marker_id, who, is_robot))
        print(f"ID {marker_id:2d} ({who}): {pure_path}")
        print(f"          print sheet: {sheet_path}")

    pdf_path = os.path.join(OUT_DIR, "print_a4_markers.pdf")
    pdf_pages.append(make_corner_page())
    pdf_pages[0].save(pdf_path, save_all=True, append_images=pdf_pages[1:],
                      resolution=DPI, title="VisionBot ArUco markers (8 cm)")
    print(f"          A4 PDF (3 pages, page 3 = arena corners): {pdf_path}")

    print("\nPrint print_a4_markers.pdf at 100% scale - the black square must")
    print("measure 8 x 8 cm (use the check bar with a ruler). If the print")
    print("comes out a bit off, that is okay for detection, but write the")
    print("real size in the project log.")
    print("\nPage 3 (optional but recommended): cut the four corner markers")
    print("and tape them flat inside the arena corners, matching the labels")
    print("(TL=30, TR=31, BR=32, BL=33 as the CAMERA sees the picture).")


if __name__ == "__main__":
    main()
