"""Generate synthetic robustness clips for the camera agent (tests/fixtures/cv_*.avi).

Stick-figure silhouettes on a noisy background with brightness flicker. These
check the decision logic and foreground extraction under motion/noise; they do
NOT replace rehearsal with real people on the demo laptop.
"""
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).resolve().parent / "fixtures"
W, H, FPS = 640, 360, 15
rng = np.random.default_rng(7)
BG = cv2.GaussianBlur(rng.integers(50, 110, (H, W, 3)).astype(np.uint8), (9, 9), 0)
SKIN, SHIRT = (150, 170, 200), (60, 90, 180)


def frame(draw=None, flicker=0):
    f = cv2.add(BG, rng.integers(0, 8, (H, W, 3)).astype(np.uint8))
    if flicker:
        f = cv2.convertScaleAbs(f, alpha=1.0, beta=int(rng.integers(-flicker, flicker + 1)))
    if draw:
        draw(f)
    return f


def standing(x, y_feet=330, h=190):
    def d(f):
        cv2.circle(f, (x, y_feet - h + 18), 16, SKIN, -1)
        cv2.rectangle(f, (x - 22, y_feet - h + 36), (x + 22, y_feet - h + 110), SHIRT, -1)
        cv2.line(f, (x - 10, y_feet - h + 110), (x - 14, y_feet), SHIRT, 14)
        cv2.line(f, (x + 10, y_feet - h + 110), (x + 14, y_feet), SHIRT, 14)
    return d


def crouching(x, y_feet=330):
    def d(f):
        cv2.circle(f, (x, y_feet - 118), 16, SKIN, -1)
        cv2.rectangle(f, (x - 24, y_feet - 100), (x + 24, y_feet - 40), SHIRT, -1)
        cv2.rectangle(f, (x - 26, y_feet - 42), (x + 30, y_feet), SHIRT, -1)
    return d


def lying(x, y_floor=330):
    def d(f):
        cv2.circle(f, (x, y_floor - 22), 16, SKIN, -1)
        cv2.rectangle(f, (x + 16, y_floor - 42), (x + 96, y_floor - 4), SHIRT, -1)
        cv2.line(f, (x + 96, y_floor - 30), (x + 180, y_floor - 26), SHIRT, 14)
        cv2.line(f, (x + 96, y_floor - 14), (x + 180, y_floor - 10), SHIRT, 14)
    return d


def write(name, frames):
    w = cv2.VideoWriter(str(OUT / name), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    for f in frames:
        w.write(f)
    w.release()


def empty(n, flicker=0):
    return [frame(flicker=flicker) for _ in range(n)]


def main():
    OUT.mkdir(exist_ok=True)
    # walk across the view, never falls -> expect 0 alerts
    write("cv_walk.avi", empty(50, 6) + [frame(standing(80 + i * 9), 6) for i in range(55)] + empty(10, 6))
    # walk in, crouch to tie a shoe, stand, leave -> expect 0 alerts
    write("cv_crouch.avi", empty(50, 6) + [frame(standing(200 + i * 4), 6) for i in range(25)]
          + [frame(crouching(300), 6) for _ in range(35)] + [frame(standing(300 + i * 6), 6) for i in range(25)])
    # walk in, fall, lie still 3 s with lighting flicker -> expect 1 alert
    write("cv_fall_flicker.avi", empty(50, 8) + [frame(standing(150 + i * 5), 8) for i in range(30)]
          + [frame(crouching(300), 8) for _ in range(3)] + [frame(lying(260), 8) for _ in range(45)])
    print("clips written to", OUT)


if __name__ == "__main__":
    main()
