#!/usr/bin/env python3
"""palomas — two doves, corzo y miranda, crossing a dusk sky in ASCII.

    python palomas.py                  # animate in the terminal (Ctrl-C to stop)
    python palomas.py --render         # write palomas.gif + palomas.mp4
    python palomas.py --dump 3.2       # print the raw character grid at t=3.2s

Design
------
Nothing here is a font artefact or a pre-made sprite sheet. The sky is an fBM
haze field, the city is a procedural silhouette with flickering windows, and
each dove is a signed shape (body ellipse, head, beak, tail fan, two rotating
wing capsules with primary feathers) rasterised by supersampling into a density
ramp. The wingbeat is a real rotation, so the silhouette changes every frame
instead of snapping between poses.

    corzo    bronze, wider span, slow deliberate beat, leads and dives
    miranda  ivory, faster beat, weaves below and cuts across
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------------------------------------------------------------- canvas ----
W, H = 132, 56
FPS = 20
DURATION = 9.0
FONT_PATH = r"C:\Windows\Fonts\consola.ttf"
FONT_SIZE = 18
SS = 3  # supersampling per cell when rasterising a dove


# ---------------------------------------------------------------- colour ----
def hexc(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    t = min(max(t, 0.0), 1.0)
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(3))


def mul(c, k):
    return tuple(min(255, max(0, int(v * k))) for v in c)


INK = hexc("07070e")
SKY_TOP = hexc("10102b")
SKY_MID = hexc("3b2a58")
SKY_LOW = hexc("874b6d")
SKY_HORIZON = hexc("d08a5e")
STAR = hexc("e6e9ff")
STAR_DIM = hexc("7f84ad")
CITY = hexc("0d0b16")
CITY_EDGE = hexc("221a30")
WINDOW = hexc("ffcc7a")
HAZE = hexc("6d4a6e")

CORZO_BODY = hexc("d9954a")
CORZO_WING = hexc("8f5526")
CORZO_RIM = hexc("ffd39a")
CORZO_GLOW = hexc("ff9b3d")

MIRANDA_BODY = hexc("d7e0f2")
MIRANDA_WING = hexc("8095bd")
MIRANDA_RIM = hexc("ffffff")
MIRANDA_GLOW = hexc("8fd8ff")

TITLE = hexc("f6efe3")
LABEL_C = hexc("e8dcc8")

SKY_RAMP = " ..::;;,,----~~~~"
BIRD_RAMP = " .:-=+*#%@"


# ------------------------------------------------------------- utilities ----
def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lerp_to(u, a, b):
    return a + (b - a) * u


def noise2(x, y, seed=0.0):
    def h(i, j):
        n = math.sin(i * 127.1 + j * 311.7 + seed * 74.7) * 43758.5453
        return n - math.floor(n)
    xi, yi = math.floor(x), math.floor(y)
    u, v = smoothstep(x - xi), smoothstep(y - yi)
    a = h(xi, yi) * (1 - u) + h(xi + 1, yi) * u
    b = h(xi, yi + 1) * (1 - u) + h(xi + 1, yi + 1) * u
    return a * (1 - v) + b * v


def fbm(x, y, octaves=4, seed=0.0):
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for i in range(octaves):
        total += amp * noise2(x * freq, y * freq, seed + i * 3.1)
        norm += amp
        amp *= 0.5
        freq *= 2.03
    return total / norm


class Frame:
    """Character grid plus a colour per cell."""

    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.ch = np.full((h, w), " ", dtype="<U1")
        self.co = np.zeros((h, w, 3), dtype=np.int16)

    def put(self, x, y, c, col):
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < self.w and 0 <= yi < self.h:
            self.ch[yi, xi] = c
            self.co[yi, xi] = col

    def text(self, x, y, s, col):
        for i, c in enumerate(s):
            if c != " ":
                self.put(x + i, y, c, col)


# ------------------------------------------------------------------ sky ----
def draw_sky(f: Frame, t: float):
    for y in range(H):
        v = y / (H - 1)
        if v < 0.42:
            base = mix(SKY_TOP, SKY_MID, smoothstep(v / 0.42))
        elif v < 0.76:
            base = mix(SKY_MID, SKY_LOW, smoothstep((v - 0.42) / 0.34))
        else:
            base = mix(SKY_LOW, SKY_HORIZON, smoothstep((v - 0.76) / 0.24))
        base = mul(base, 0.62 + 0.55 * smoothstep((v - 0.55) / 0.45))

        for x in range(W):
            dens = fbm(x * 0.055 + t * 0.32, y * 0.16 - t * 0.06, 4, 1.7)
            band = 0.5 + 0.5 * math.sin(y * 0.42 - t * 0.9 + dens * 5.0)
            dens = dens * 0.82 + band * 0.18
            if dens < 0.62:                      # sparse: most of the sky stays empty
                f.put(x, y, " ", base)
                continue
            k = (dens - 0.62) / 0.38
            idx = min(len(SKY_RAMP) - 1, int(k * len(SKY_RAMP)))
            col = mix(base, mix(base, HAZE, 0.55), k * 0.9)
            f.put(x, y, SKY_RAMP[idx], col)


def make_stars(n=140, seed=5):
    rng = np.random.default_rng(seed)
    return [(int(rng.integers(0, W)), int(rng.integers(0, int(H * 0.62))),
             float(rng.random() * 6.28), float(0.45 + rng.random() * 0.7))
            for _ in range(n)]


def draw_stars(f: Frame, t: float, stars):
    for (x, y, phase, bright) in stars:
        tw = 0.5 + 0.5 * math.sin(t * 2.1 + phase)
        fade = max(0.0, 1.0 - (y / (H * 0.66)) ** 2)
        val = bright * tw * fade
        if val < 0.28:
            continue
        c = "." if val < 0.55 else ("+" if val < 0.85 else "*")
        f.put(x, y, c, mix(STAR_DIM, STAR, val))


# ----------------------------------------------------------------- city ----
def make_city(seed=11):
    rng = np.random.default_rng(seed)
    blocks, x = [], -3
    while x < W + 4:
        w = int(rng.integers(6, 14))
        h = int(rng.integers(5, 15))
        blocks.append((x, w, h))
        x += w + int(rng.integers(0, 3))
    return blocks


def draw_city(f: Frame, t: float, blocks):
    horizon = H - 3
    for (bx, bw, bh) in blocks:
        top = horizon - bh
        for yy in range(top, H - 1):
            for xx in range(bx, bx + bw):
                if not (0 <= xx < W):
                    continue
                if yy == top:
                    f.put(xx, yy, "_", CITY_EDGE)
                elif xx in (bx, bx + bw - 1):
                    f.put(xx, yy, "|", CITY_EDGE)
                else:
                    f.put(xx, yy, " ", CITY)
        for yy in range(top + 2, horizon, 3):
            for xx in range(bx + 2, bx + bw - 2, 3):
                if noise2(xx * 3.1, yy * 2.7, 9.0) > 0.63:
                    fl = 0.70 + 0.30 * math.sin(t * 2.6 + xx * 0.7 + yy * 1.3)
                    if fl > 0.82:
                        f.put(xx, yy, "=", mix(mix(CITY, WINDOW, 0.45), WINDOW, fl))
    for xx in range(W):
        f.put(xx, H - 1, "_", mix(CITY, SKY_HORIZON, 0.16))
        if noise2(xx * 0.8, t * 1.8, 3.0) > 0.78:
            f.put(xx, H - 1, ",", mix(SKY_LOW, WINDOW, 0.22))


# ----------------------------------------------------------------- dove ----
def _stroke(f, pts, col):
    """One glyph per cell along a polyline — a drawn line, not a hatched band."""
    last = None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        n = int(max(abs(dx), abs(dy)) * 2) + 1
        for i in range(n + 1):
            t = i / n
            x, y = x0 + dx * t, y0 + dy * t
            cell = (int(round(x)), int(round(y)))
            if cell == last:
                continue
            last = cell
            if abs(dy) < 0.45 * abs(dx):
                c = "_"
            elif abs(dx) < 0.45 * abs(dy):
                c = "|"
            else:
                c = "\\" if dx * dy > 0 else "/"
            f.put(x, y, c, col)


def _quad(p0, p1, p2, n=12):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / n for i in range(n + 1))]


ASPECT = 0.57          # rows are ~1.75x taller than columns are wide: compress y


def draw_dove(f: Frame, cx, cy, phase, span, body_c, wing_c, rim_c, glow_c, trail=None):
    """A dove: a body glyph, plus one wing arc above it.

    Vertical offsets are multiplied by ASPECT (~0.57) because a character row is
    about 1.75x taller than a column is wide; without that compression a wing
    becomes a totem pole. The wing is drawn with diagonal glyphs only — horizontal
    `_` runs turned it into a ladder.
    """
    k = span / 12.0

    def wing(cxx, cyy, ph, tint, strength):
        up_ = math.sin(ph)
        rise = 7.4 + 3.4 * up_
        sh = (cxx - 1.0 * k, cyy - 0.9 * ASPECT * k)
        ctrl = (cxx - 1.9 * k, cyy - (0.58 * rise + 0.9) * ASPECT * k)
        tip = (cxx - 3.8 * k, cyy - (rise + 0.8) * ASPECT * k)
        pts = _quad(sh, ctrl, tip, 26)
        last = None
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            cell = (int(round(x1)), int(round(y1)))
            if cell == last:
                continue
            last = cell
            c = chr(92) if (x1 - x0) * (y1 - y0) >= 0 else "/"
            f.put(x1, y1, c, tint)
        for fx, fy in ((0.3, -0.55), (0.9, -0.2), (1.4, 0.25)):
            f.put(tip[0] + fx * k, tip[1] + fy * ASPECT * k * 1.8, "'",
                  mix(tint, rim_c, 0.5 * strength))

    for (gx, gy, gk) in (trail or []):
        wing(cx + gx, cy + gy, phase - 0.55, mul(wing_c, 0.5 * gk), 0.4)
        f.text(cx + gx - 3.1 * k, cy + gy + 0.5 * ASPECT * k,
               chr(92) + "_", mul(body_c, 0.5 * gk))

    wing(cx, cy, phase, mix(wing_c, rim_c, 0.30), 1.0)

    base = cy + 0.5 * ASPECT * k
    f.text(cx - 3.1 * k, base, chr(92) + "_", body_c)
    f.put(cx - 1.1 * k, base, "(", body_c)
    f.put(cx - 0.1 * k, base, "o", mix(rim_c, glow_c, 0.5))
    f.put(cx + 0.9 * k, base, ">", glow_c)


def draw_label(f: Frame, x, y, name, col):
    """A name pinned under its dove with a hairline pointer."""
    f.put(x, y, "'", mix(col, INK, 0.45))
    f.text(x + 1, y, name, col)
    f.put(x + len(name) + 1, y, "'", mix(col, INK, 0.45))


# ------------------------------------------------------------- feathers ----
def make_feathers(n=70, seed=3):
    rng = np.random.default_rng(seed)
    return [{
        "x": float(rng.uniform(0, W)), "y": float(rng.uniform(6, H - 12)),
        "vx": float(rng.uniform(-0.16, -0.05)), "vy": float(rng.uniform(0.10, 0.24)),
        "sway": float(rng.uniform(0.7, 1.9)), "ph": float(rng.uniform(0, 6.28)),
        "c": str(rng.choice([",", "'", "`", "\\", "/"])),
    } for _ in range(n)]


def draw_feathers(f: Frame, t, feathers, near_y, intensity=0.5):
    for p in feathers:
        if p["vy"] * t * 12 < 1.0:            # stagger their entrance
            continue
        x = (p["x"] + p["vx"] * t * 12 + math.sin(t * p["sway"] + p["ph"]) * 1.4) % W
        y = (p["y"] + p["vy"] * t * 12) % (H - 10)
        d = abs(y - near_y)
        if d > 16:
            continue
        fade = max(0.0, 1.0 - d / 16) * intensity
        f.put(x, y, p["c"], mix(SKY_MID, MIRANDA_BODY, 0.45 * fade))


# ----------------------------------------------------------------- text ----
def draw_title(f: Frame, t, s="palomas", y=None):
    if t < 6.1:
        return
    y = H - 22 if y is None else y
    reveal = (t - 6.1) / 1.5
    spaced = " ".join(s)
    x0 = int(W / 2 - len(spaced) / 2)
    for i, c in enumerate(spaced):
        if c == " ":
            continue
        fade = min(1.0, max(0.0, reveal * len(s) * 1.4 - i / 2))
        if fade <= 0:
            continue
        f.put(x0 + i, y, c, mix(mix(SKY_LOW, TITLE, 0.5), TITLE, fade))
    if t > 7.1:
        sub = "corzo  &  miranda"
        sx = int(W / 2 - len(sub) / 2)
        fade = min(1.0, (t - 7.1) / 1.3)
        f.text(sx, y + 2, sub, mix(SKY_MID, LABEL_C, 0.75 * fade))


# ---------------------------------------------------------------- paths ----
def paths(t):
    """(x, y, beat_phase, scale) for corzo and miranda."""
    u = smoothstep(t / DURATION)

    cx = lerp_to(u, -16, W * 0.84) + 3.6 * math.sin(u * 5.2)
    cy = (14.0
          + 4.6 * math.sin(u * 4.4 + 0.35)
          - 7.0 * math.exp(-((u - 0.50) ** 2) / 0.010)
          + 1.6 * math.sin(u * 10.0))

    mu = smoothstep(max(0.0, (t - 0.6) / (DURATION - 0.5)))
    mx = lerp_to(mu, -24, W * 0.74) + 2.8 * math.sin(mu * 6.6 + 1.0)
    my = (28.0
          + 4.8 * math.sin(mu * 6.0 + 2.2)
          - 8.4 * math.exp(-((mu - 0.55) ** 2) / 0.008)
          + 1.4 * math.sin(mu * 13.0))

    return (cx, cy, t * 6.4, 1.10), (mx, my, t * 9.4 + 1.2, 0.86)


# ---------------------------------------------------------------- scene ----
def scene(t: float, stars, city, feathers, title=True):
    f = Frame()
    draw_sky(f, t)
    draw_stars(f, t, stars)
    draw_city(f, t, city)

    (cx, cy, cph, _cs), (mx, my, mph, _ms) = paths(t)
    draw_feathers(f, t, feathers, (cy + my) / 2, 0.55 if t < 5.0 else 0.9)

    draw_dove(f, mx, my, mph, 16.0, MIRANDA_BODY, MIRANDA_WING, MIRANDA_RIM, MIRANDA_GLOW,
)
    draw_dove(f, cx, cy, cph, 20.0, CORZO_BODY, CORZO_WING, CORZO_RIM, CORZO_GLOW,
)

    if 2 < cx < W - 10:
        draw_label(f, int(cx) - 3, int(cy) + 4, "corzo", mix(CORZO_GLOW, LABEL_C, 0.5))
    if 2 < mx < W - 12:
        draw_label(f, int(mx) - 4, int(my) + 4, "miranda", mix(MIRANDA_GLOW, LABEL_C, 0.55))

    if title:
        draw_title(f, t)
    return f


# ------------------------------------------------------------ rasterise ----
def load_font():
    try:
        return ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError:
        return ImageFont.load_default()


def cell_size(font):
    ascent, descent = font.getmetrics()
    box = font.getbbox("M")
    return box[2] - box[0], ascent + descent


def rasterize(f: Frame, font, cw, ch):
    img = Image.new("RGB", (f.w * cw, f.h * ch), INK)
    d = ImageDraw.Draw(img)
    for y in range(f.h):
        for x in range(f.w):
            c = f.ch[y, x]
            if c == " ":
                continue
            d.text((x * cw, y * ch), c, font=font, fill=tuple(int(v) for v in f.co[y, x]))
    return img


def render(out_gif="palomas.gif", out_mp4="palomas.mp4", frames_dir=None):
    font = load_font()
    cw, ch = cell_size(font)
    w, h = W * cw, H * ch
    n = int(DURATION * FPS)
    stars, city, feathers = make_stars(), make_city(), make_feathers()

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", f"{w}x{h}", "-framerate", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-movflags", "+faststart", out_mp4],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    frames = []
    for i in range(n):
        t = i / FPS
        img = rasterize(scene(t, stars, city, feathers), font, cw, ch)
        proc.stdin.write(img.tobytes())
        frames.append(img)
        if frames_dir:
            os.makedirs(frames_dir, exist_ok=True)
            img.save(os.path.join(frames_dir, f"f{i:04d}.png"))
        if i % 30 == 0:
            print(f"  frame {i}/{n}", flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"wrote {out_mp4}  ({w}x{h}, {n} frames)")

    tmp = "_gif_frames"
    os.makedirs(tmp, exist_ok=True)
    for j, img in enumerate(frames[::2]):
        img.save(os.path.join(tmp, f"g{j:04d}.png"))
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS // 2),
         "-i", os.path.join(tmp, "g%04d.png"),
         "-vf", ("scale=1100:-1:flags=lanczos,split[a][b];"
                 "[a]palettegen=max_colors=256:stats_mode=diff[p];"
                 "[b][p]paletteuse=dither=sierra2_4a"),
         "-loop", "0", out_gif], check=True)
    for fn in os.listdir(tmp):
        os.remove(os.path.join(tmp, fn))
    os.rmdir(tmp)
    print(f"wrote {out_gif}  ({os.path.getsize(out_gif) // 1024} KB)")


# -------------------------------------------------------------- terminal ----
def terminal_loop(loops=3):
    stars, city, feathers = make_stars(), make_city(), make_feathers()
    n = int(DURATION * FPS)
    sys.stdout.write("\x1b[?25l\x1b[2J")
    try:
        for _ in range(loops):
            for i in range(n):
                f = scene(i / FPS, stars, city, feathers)
                out = []
                for y in range(H):
                    row, last = [], None
                    for x in range(W):
                        c = tuple(int(v) for v in f.co[y, x])
                        if c != last:
                            row.append(f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m")
                            last = c
                        row.append(f.ch[y, x])
                    out.append("".join(row))
                sys.stdout.write("\x1b[H" + "\n".join(out) + "\x1b[0m")
                sys.stdout.flush()
                time.sleep(1 / FPS)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[0m\n")


def dump(t):
    print("\n".join("".join(r) for r in scene(t, make_stars(), make_city(), make_feathers()).ch))


def main():
    ap = argparse.ArgumentParser(description="ASCII doves at dusk")
    ap.add_argument("--render", action="store_true", help="write palomas.gif and palomas.mp4")
    ap.add_argument("--dump", type=float, metavar="T", help="print the grid at time T seconds")
    ap.add_argument("--frames", metavar="DIR", help="also save PNG frames")
    ap.add_argument("--loops", type=int, default=3)
    a = ap.parse_args()

    if a.dump is not None:
        dump(a.dump)
    elif a.render:
        render(frames_dir=a.frames)
    else:
        terminal_loop(a.loops)


if __name__ == "__main__":
    main()
