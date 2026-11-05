"""Regenerate the README's terminal screenshots and exact plain-text fixtures.

From a source checkout with the dev extra installed:
    python examples/readme_charts.py

Pillow is already a Matplotlib dependency. Only labels use Matplotlib's bundled
DejaVu Sans Mono; drawing glyphs use cell geometry, never font fallback.
"""
from pathlib import Path
import re
import sys

# Also support direct execution, as in the README.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from PIL import Image, ImageDraw, ImageFont

from examples.gallery import CHARTS
from trendsetter_axi import render_figure

IDS = ("01_mpl_line", "04_mpl_bar", "10_mpl_imshow")
DOCS = Path(__file__).resolve().parents[1] / "docs"
SGR = re.compile(r"\x1b\[([0-9;]*)m")
BG, FG = (13, 17, 23), (230, 237, 243)
CELL_W, CELL_H, PAD = 12, 24, 16
# Draw at 2x for crisp labels and dots when GitHub scales the image down.
SCALE = 2
BOX = {"─": "lr", "│": "ud", "┌": "rd", "┐": "ld", "└": "ru", "┘": "lu"}


def draw_glyph(draw, x, y, char, color, font):
    """Draw one fixed-size terminal cell, with no inter-line leading."""
    w, h = CELL_W * SCALE, CELL_H * SCALE
    if 0x2800 <= ord(char) <= 0x28FF:
        bits = ord(char) - 0x2800
        for bit, (col, row) in enumerate(((0, 0), (0, 1), (0, 2), (1, 0),
                                         (1, 1), (1, 2), (0, 3), (1, 3))):
            if bits & (1 << bit):
                cx, cy = x + (col + 0.5) * w / 2, y + (row + 0.5) * h / 4
                r = 1.4 * SCALE
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    elif char in BOX:
        cx, cy = x + w // 2, y + h // 2
        # Rectangles keep both directions on the same pixel rows/columns;
        # Pillow's even-width line strokes offset opposite directions.
        arms = {"l": (x, cy, cx + SCALE - 1, cy + SCALE - 1),
                "r": (cx, cy, x + w - 1, cy + SCALE - 1),
                "u": (cx, y, cx + SCALE - 1, cy + SCALE - 1),
                "d": (cx, cy, cx + SCALE - 1, y + h - 1)}
        for arm in BOX[char]:
            draw.rectangle(arms[arm], fill=color)
    elif char in "▁▂▃▄▅▆▇█":
        height = (ord(char) - ord("▁") + 1) * h // 8
        draw.rectangle((x, y + h - height, x + w - 1, y + h - 1), fill=color)
    elif char in "░▒▓":
        # Ordered stippling gives 25/50/75% ink; identical foreground/background
        # ANSI colors (as used by heatmap cells) naturally become solid fills.
        level = "░▒▓".index(char) + 1
        for row in range(CELL_H):
            for col in range(CELL_W):
                if ((0, 2), (3, 1))[row % 2][col % 2] < level:
                    px, py = x + col * SCALE, y + row * SCALE
                    draw.rectangle((px, py, px + SCALE - 1, py + SCALE - 1), fill=color)
    elif char.isascii():
        draw.text((x, y + 19 * SCALE), char, font=font, fill=color, anchor="ls")
    else:
        raise ValueError(f"No cell geometry for {char!r}; add it before regenerating")


def screenshot(text):
    """Paint renderer-generated 24-bit ANSI text on a dark terminal background."""
    lines = text.splitlines()
    plain = SGR.sub("", text)
    cols = max(map(len, plain.splitlines()))
    image = Image.new("RGB", ((cols * CELL_W + 2 * PAD) * SCALE,
                              (len(lines) * CELL_H + 2 * PAD) * SCALE), BG)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(findfont(FontProperties(family="DejaVu Sans Mono")), 20 * SCALE)
    foreground, background = FG, BG
    for row, line in enumerate(lines):
        col, pos = 0, 0
        while pos < len(line):
            if match := SGR.match(line, pos):
                codes = [int(n) for n in match[1].split(";") if n] or [0]
                i = 0
                while i < len(codes):
                    code = codes[i]
                    if code == 0:
                        foreground, background = FG, BG
                    elif code in (38, 48) and codes[i + 1:i + 2] == [2]:
                        rgb = tuple(codes[i + 2:i + 5])
                        if len(rgb) != 3:
                            raise ValueError("Incomplete ANSI RGB color")
                        if code == 38:
                            foreground = rgb
                        else:
                            background = rgb
                        i += 4
                    else:
                        raise ValueError(f"Unsupported ANSI style: {codes}")
                    i += 1
                pos = match.end()
                continue
            char = line[pos]
            x, y = (PAD + col * CELL_W) * SCALE, (PAD + row * CELL_H) * SCALE
            draw.rectangle((x, y, x + CELL_W * SCALE - 1, y + CELL_H * SCALE - 1), fill=background)
            draw_glyph(draw, x, y, char, foreground, font)
            col += 1
            pos += 1
    return image


def main():
    DOCS.mkdir(exist_ok=True)
    for chart_id in IDS:
        chart = next(c for c in CHARTS if c["id"] == chart_id)
        with plt.rc_context(plt.rcParamsDefault):
            fig = chart["make"]()
            try:
                text = render_figure(fig, 80, color=True)
            finally:
                plt.close(fig)
        plain = SGR.sub("", text)
        (DOCS / f"{chart_id}.txt").write_text(plain, encoding="utf-8")
        path = DOCS / f"{chart_id}.png"
        screenshot(text).save(path, optimize=True)
        if path.stat().st_size >= 300_000:
            raise ValueError(f"{path} exceeds the README image budget")
        print(f"{path.relative_to(DOCS.parent)} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
