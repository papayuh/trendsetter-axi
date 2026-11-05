#!/usr/bin/env python3
"""Re-record the actual packaged viewer through a PTY, plus its static screenshot.

Dev-only dependencies: Pillow, pyte. Run from repo root:
  python examples/record_interaction.py /path/to/monospace.ttf

No viewer code is mocked. The child opens a real matplotlib Figure with interact;
this script sends standard SGR mouse reports, captures its terminal, and presses q.
"""
import argparse
from contextlib import ExitStack
import fcntl
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import termios
import time

COLS, ROWS, CW, CH, FPS = 120, 38, 10, 20, 10
BG, FG = (15, 17, 21), (225, 225, 225)
ROOT = Path(__file__).resolve().parents[1]


def rgb(value, default):
    try:
        return tuple(bytes.fromhex(value)) if len(value) == 6 else default
    except ValueError:
        return default


def screenshot(screen, font, cache):
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (COLS * CW, ROWS * CH), BG)
    for y in range(ROWS):
        for x in range(COLS):
            cell = screen.buffer[y][x]
            fg, bg = rgb(cell.fg, FG), rgb(cell.bg, BG)
            key = (cell.data, fg, bg)
            if key not in cache:
                tile = Image.new('RGB', (CW, CH), bg)
                d = ImageDraw.Draw(tile)
                char = cell.data or ' '
                o = ord(char) if len(char) == 1 else 0
                if 0x2800 <= o <= 0x28ff:
                    for bit, (a, b) in enumerate([(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]):
                        if (o - 0x2800) >> bit & 1:
                            px, py = 2 + a * 4, 2 + b * 4 + (1 if b > 1 else 0)
                            d.rectangle([px, py, px + 2, py + 2], fill=fg)
                elif char == '█':
                    d.rectangle([0, 0, CW, CH], fill=fg)
                elif char == '▀':
                    d.rectangle([0, 0, CW, CH // 2 - 1], fill=fg)
                elif 0x2581 <= o <= 0x2587:
                    d.rectangle([0, CH - round((o - 0x2580) * CH / 8), CW, CH], fill=fg)
                elif 0x2589 <= o <= 0x258f:
                    d.rectangle([0, 0, round((0x2590 - o) * CW / 8) - 1, CH], fill=fg)
                elif char in '─│┌┐└┘┤':
                    mx, my = CW // 2, CH // 2
                    if char == '─':
                        d.line([(0, my), (CW, my)], fill=fg)
                    if char == '│':
                        d.line([(mx, 0), (mx, CH)], fill=fg)
                    if char in '┌┐':
                        d.line([(mx, my), (mx, CH)], fill=fg)
                    if char in '└┘':
                        d.line([(mx, 0), (mx, my)], fill=fg)
                    if char in '┌└':
                        d.line([(mx, my), (CW, my)], fill=fg)
                    if char in '┐┘┤':
                        d.line([(0, my), (mx, my)], fill=fg)
                    if char == '┤':
                        d.line([(mx, 0), (mx, CH)], fill=fg)
                elif char != ' ':
                    d.text((CW / 2, CH / 2), char, font=font, fill=fg, anchor='mm')
                cache[key] = tile
            im.paste(cache[key], (x * CW, y * CH))
    return im


def report(button, col, row, up=False):
    return f'\x1b[<{button};{col + 1};{row + 1}{"m" if up else "M"}'.encode()


def script():
    # The packaged viewer's 120x38 layout is 68x25 cells at (8,6).
    def cell(x, y):
        return round(8 + x / 120 * 67), round(6 + (1 - y / 100) * 24)
    events = []
    def move(start, end, at, duration, drag=False):
        for i in range(1, round(duration * FPS) + 1):
            t = i / round(duration * FPS)
            t = t * t * (3 - 2 * t)
            col, row = [round(a + (b - a) * t) for a, b in zip(start, end)]
            events.append((at + duration * i / round(duration * FPS), report(32 if drag else 35, col, row), (col, row)))
    hover = cell(58, 62)
    move((70, 30), hover, 2, 1)
    a, b = cell(6, 52), cell(42, 6)
    move(hover, a, 4, .7)
    events.append((4.8, report(0, *a), a))
    move(a, b, 4.9, 2, True)
    events.append((7, report(0, *b, up=True), b))
    # Move the same brush across the three source series.
    a, b = cell(24, 29), cell(58, 62)
    move(cell(42, 6), a, 8, .6)
    events.append((8.7, report(0, *a), a))
    move(a, b, 8.8, 2, True)
    events.append((10.9, report(0, *b, up=True), b))
    a, b = cell(58, 62), cell(92, 36)
    events.append((12, report(0, *a), a))
    move(a, b, 12.1, 2, True)
    events.append((14.2, report(0, *b, up=True), b))
    events.append((16, b'q', b))
    return sorted(events)


def stop(child):
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def main():
    import pyte
    from PIL import ImageDraw, ImageFont
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('font')
    args = parser.parse_args()
    font = ImageFont.truetype(args.font, 16)
    cache = {}
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.ByteStream(screen)
    static = subprocess.run([sys.executable, str(ROOT / 'examples/scatter_brush.py'), '--static'],
                            check=True, capture_output=True).stdout
    stream.feed(static.rstrip(b'\r\n'))
    screenshot(screen, font, cache).save(ROOT / 'docs/scatter-styled.png')
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.ByteStream(screen)
    events, frames, index = script(), [], 0
    pos = (70, 30)
    with ExitStack() as cleanup:
        master, slave = pty.openpty()
        cleanup.callback(os.close, master)
        cleanup.callback(os.close, slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLS, 0, 0))
        before = termios.tcgetattr(slave)
        child = subprocess.Popen([sys.executable, str(ROOT / 'examples/scatter_brush.py')],
                                 stdin=slave, stdout=slave, stderr=slave,
                                 env=dict(os.environ, TERM='xterm-256color'), start_new_session=True)
        cleanup.callback(stop, child)
        start = time.monotonic()
        for frame in range(166):
            now = frame / FPS
            while index < len(events) and events[index][0] <= now:
                _, data, pos = events[index]
                os.write(master, data)
                index += 1
            deadline = start + (frame + 1) / FPS
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], max(0, deadline - time.monotonic()))
                if not ready:
                    break
                stream.feed(os.read(master, 1 << 16))
            if frame < 160:
                im = screenshot(screen, font, cache)
                draw = ImageDraw.Draw(im)
                px, py = pos[0] * CW + CW // 2, pos[1] * CH + CH // 2
                draw.polygon([(px + x, py + y) for x, y in [(0, 0), (0, 18), (4, 14), (8, 22), (11, 21), (8, 13), (14, 13)]],
                             fill=(245, 245, 242), outline=(20, 20, 20))
                frames.append(im.quantize(colors=128))
        if child.wait(timeout=3) != 0:
            raise RuntimeError('viewer did not exit cleanly')
        if termios.tcgetattr(slave) != before:
            raise RuntimeError('viewer failed to restore terminal settings')
    if not frames:
        raise RuntimeError('no terminal frames captured')
    frames[0].save(ROOT / 'docs/scatter-brush.gif', save_all=True, append_images=frames[1:],
                   duration=1000 // FPS, loop=0, disposal=2, optimize=True)
    print('Recorded real packaged viewer; q exit and terminal restoration verified.')


if __name__ == '__main__':
    main()
