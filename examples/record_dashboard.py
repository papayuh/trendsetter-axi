#!/usr/bin/env python3
"""Record the real dashboard, including live refresh and mouse input, via PTY.

Dev-only dependencies: Pillow, pyte. From the repo root:
  python examples/record_dashboard.py /path/to/monospace.ttf

Writes docs/dashboard.png and docs/dashboard-live.gif. No drawing code is mocked;
uses the same cell-to-pixel capture as record_interaction.py and verifies cleanup.
"""
import argparse
from contextlib import ExitStack
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

import record_interaction as capture

COLS, ROWS, FPS = 140, 44, 8
ROOT = capture.ROOT


def events():
    # Tile-local plot (7,4), translated into the real 140x44 dashboard grid.
    # Hover the bar, then brush the scatter between refreshes at t=3 and t=6.
    sequence = [(1.0, capture.report(35, 96, 12), (96, 12)),
                (3.4, capture.report(0, 13, 30), (13, 30))]
    for i in range(1, 13):
        col, row = round(13 + 26 * i / 12), round(30 + 6 * i / 12)
        sequence.append((3.4 + i / 10, capture.report(32, col, row), (col, row)))
    sequence.extend([(4.7, capture.report(0, 39, 36, up=True), (39, 36)),
                     (6.7, b'x', (39, 36)),
                     (7.4, capture.report(35, 50, 12), (50, 12))])
    return sequence


def main():
    import pyte
    from PIL import ImageDraw, ImageFont

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('font')
    args = parser.parse_args()
    capture.COLS, capture.ROWS = COLS, ROWS
    font = ImageFont.truetype(args.font, 16)
    cache = {}
    static = subprocess.run([sys.executable, str(ROOT / 'examples/dashboard_demo.py'),
                             '--cols', str(COLS), '--rows', str(ROWS)],
                            check=True, capture_output=True).stdout
    screen = pyte.Screen(COLS, ROWS)
    pyte.ByteStream(screen).feed(static.rstrip(b'\r\n'))
    capture.screenshot(screen, font, cache).save(ROOT / 'docs/dashboard.png')

    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.ByteStream(screen)
    frames, sequence, index, pos = [], events(), 0, (96, 12)
    with ExitStack() as cleanup:
        master, slave = pty.openpty()
        cleanup.callback(os.close, master)
        cleanup.callback(os.close, slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLS, 0, 0))
        before = termios.tcgetattr(slave)
        child = subprocess.Popen([sys.executable, str(ROOT / 'examples/dashboard_demo.py'),
                                  '--live', '--interval', '3'], stdin=slave, stdout=slave, stderr=slave,
                                 env=dict(os.environ, TERM='xterm-256color'), start_new_session=True)
        cleanup.callback(capture.stop, child)
        ready_by = time.monotonic() + 20
        # Do not record Python's import time as blank video.
        while 'q quit' not in screen.display[-1]:
            if time.monotonic() > ready_by or child.poll() is not None:
                raise RuntimeError('dashboard did not produce its first frame')
            if select.select([master], [], [], .1)[0]:
                stream.feed(os.read(master, 1 << 18))
        start = time.monotonic()
        for frame in range(11 * FPS):
            now = frame / FPS
            while index < len(sequence) and sequence[index][0] <= now:
                _, data, pos = sequence[index]
                os.write(master, data)
                index += 1
            deadline = start + (frame + 1) / FPS
            while time.monotonic() < deadline:
                if not select.select([master], [], [], max(0, deadline - time.monotonic()))[0]:
                    break
                stream.feed(os.read(master, 1 << 18))
            im = capture.screenshot(screen, font, cache)
            draw = ImageDraw.Draw(im)
            px, py = pos[0] * capture.CW + 5, pos[1] * capture.CH + 10
            draw.polygon([(px + x, py + y) for x, y in
                          [(0, 0), (0, 18), (4, 14), (8, 22), (11, 21), (8, 13), (14, 13)]],
                         fill=(245, 245, 242), outline=(20, 20, 20))
            frames.append(im.quantize(colors=128))
        if 'update 0003' not in screen.display[1]:
            raise RuntimeError('live callback did not refresh three times')
        os.write(master, b'q')
        if child.wait(timeout=5) != 0:
            raise RuntimeError('dashboard did not exit cleanly')
        if termios.tcgetattr(slave) != before:
            raise RuntimeError('dashboard failed to restore terminal settings')
        # Drain the real terminal leave sequence too, not just termios state.
        tail = b''
        while select.select([master], [], [], .1)[0]:
            tail += os.read(master, 1 << 18)
        from trendsetter_axi.viewer import LEAVE
        if LEAVE.encode() not in tail:
            raise RuntimeError('dashboard failed to restore the cursor/mouse/screen')
    frames[0].save(ROOT / 'docs/dashboard-live.gif', save_all=True, append_images=frames[1:],
                   duration=1000 // FPS, loop=0, disposal=2, optimize=True)
    print('Recorded real dashboard: three live updates, mouse input, q exit and terminal restore verified.')


if __name__ == '__main__':
    main()
