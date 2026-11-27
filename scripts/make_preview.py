#!/usr/bin/env python3
"""Render docs/ui-preview.png, an accurate mock of sotto's note view.

This is a preview illustration, not a live screenshot: it redraws the same
layout, type scale and colours as static/index.html + static/style.css with
Pillow.  The image itself is labelled "UI preview".  Run from the repo root:

    python scripts/make_preview.py
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1440, 940
S = 2  # supersampling factor
FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
OUT = Path(__file__).resolve().parents[1] / "docs" / "ui-preview.png"

BG = (10, 11, 13)
PANEL = (16, 18, 22)
PANEL2 = (21, 24, 30)
PANEL3 = (26, 30, 38)
LINE = (35, 39, 48)
LINE_SOFT = (27, 31, 39)
INK = (236, 238, 243)
INK_DIM = (195, 199, 210)
MUTED = (138, 143, 158)
MUTED2 = (95, 101, 115)
ACCENT = (200, 241, 105)
ACCENT_INK = (16, 19, 10)
DANGER = (255, 128, 128)

SIDEBAR = 296
INNER_X = 438
INNER_W = 860

_NOTES = [
    ("Morning rehearsal — take 2", "01:52 · 6 seg", True),
    ("Client call · Acme", "23:41 · 41 seg", False),
    ("Lecture 04 — networks", "48:07 · 96 seg", False),
    ("Voice memo · ideas", "02:15 · 9 seg", False),
]

_SEGMENTS = [
    ("00:00", "Host", "Okay, let's start from the top. The room tone is a little heavy, so give me one second of silence first."),
    ("00:09", "Host", "When the chorus comes back in, I want the guitars pulled back and the vocal right up front."),
    ("00:27", "Guest", "That second pass felt much better. Can we keep the tempo but lose the click in the last bar?"),
    ("00:48", "Host", "I'll send over the stems tonight. If the low end still feels muddy, try a gentle cut around two hundred hertz."),
    ("01:12", "Host", "Let it ring for at least four seconds before the fade."),
    ("01:38", "Host", "Perfect. Let's call it a wrap before the rain starts again."),
]

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(name: str, size: float) -> ImageFont.FreeTypeFont:
    key = (name, int(size * S))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS / name), int(size * S))
    return _font_cache[key]


def sc(value: float) -> int:
    return int(round(value * S))


class Canvas:
    def __init__(self, image: Image.Image) -> None:
        self.d = ImageDraw.Draw(image)
        self.img = image

    def rect(self, x1, y1, x2, y2, radius=0, fill=None, outline=None, width=1):
        if fill is None and outline is None:
            return
        self.d.rounded_rectangle(
            [sc(x1), sc(y1), sc(x2) - 1, sc(y2) - 1],
            radius=sc(radius),
            fill=fill,
            outline=outline,
            width=max(1, sc(width)),
        )

    def gradient_rect(self, x1, y1, x2, y2, radius, top, bottom):
        width, height = sc(x2 - x1), sc(y2 - y1)
        gradient = Image.new("RGB", (1, height))
        for row in range(height):
            t = row / max(1, height - 1)
            gradient.putpixel(
                (0, row),
                tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)),
            )
        gradient = gradient.resize((width, height))
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=sc(radius), fill=255
        )
        self.img.paste(gradient, (sc(x1), sc(y1)), mask)

    def line(self, x1, y1, x2, y2, fill, width=1):
        self.d.line([sc(x1), sc(y1), sc(x2), sc(y2)], fill=fill, width=max(1, sc(width)))

    def dot(self, cx, cy, r, fill, outline=None, width=1):
        self.d.ellipse(
            [sc(cx - r), sc(cy - r), sc(cx + r), sc(cy + r)],
            fill=fill,
            outline=outline,
            width=max(1, sc(width)),
        )

    def text(self, x, y, value, f, fill, anchor="la"):
        self.d.text((sc(x), sc(y)), value, font=f, fill=fill, anchor=anchor)

    def width(self, value, f) -> float:
        return self.d.textlength(value, font=f) / S

    def track(self, x, y, value, f, fill, spacing, anchor="la"):
        total = sum(self.width(ch, f) + spacing for ch in value) - spacing
        if anchor == "ra":
            x -= total
        for ch in value:
            self.text(x, y, ch, f, fill)
            x += self.width(ch, f) + spacing
        return total

    def wrap(self, value, f, max_width) -> list[str]:
        lines, current = [], ""
        for word in value.split():
            trial = f"{current} {word}".strip()
            if self.width(trial, f) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines


def download_icon(c: Canvas, x, y, color):
    c.line(x + 6.5, y + 1, x + 6.5, y + 8, color, 1.5)
    c.line(x + 3, y + 4.5, x + 6.5, y + 8, color, 1.5)
    c.line(x + 10, y + 4.5, x + 6.5, y + 8, color, 1.5)
    c.line(x + 1.5, y + 11.5, x + 11.5, y + 11.5, color, 1.5)


def trash_icon(c: Canvas, x, y, color):
    c.line(x + 1.5, y + 3, x + 11.5, y + 3, color, 1.4)
    c.line(x + 5, y + 1.5, x + 8, y + 1.5, color, 1.4)
    c.rect(x + 2.5, y + 4.5, x + 10.5, y + 12, 1.5, outline=color, width=1.2)
    c.line(x + 5, y + 6.5, x + 5, y + 10, color, 1.2)
    c.line(x + 8, y + 6.5, x + 8, y + 10, color, 1.2)


def play_icon(c: Canvas, cx, cy):
    c.d.polygon(
        [(sc(cx - 3.2), sc(cy - 5.6)), (sc(cx - 3.2), sc(cy + 5.6)), (sc(cx + 6), sc(cy))],
        fill=ACCENT_INK,
    )


def glow_background() -> Image.Image:
    arr = np.zeros((H * S, W * S, 3), dtype=np.float32)
    arr[:, :] = BG
    yy, xx = np.mgrid[0 : H * S, 0 : W * S].astype(np.float32)

    def add_glow(cx, cy, rx, ry, color, alpha):
        d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        weight = np.clip(1 - d, 0, 1) ** 2 * alpha
        for channel in range(3):
            arr[:, :, channel] += weight * (color[channel] - BG[channel])

    add_glow(0.72 * W * S, -0.12 * H * S, 900 * S, 520 * S, ACCENT, 0.07)
    add_glow(1.00 * W * S, 1.00 * H * S, 700 * S, 500 * S, (120, 140, 255), 0.04)
    image = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for row in range(H * S):
        t = row / (H * S)
        alpha = int((0.72 - 0.37 * t) * 255)
        od.line([(0, row), (SIDEBAR * S, row)], fill=(*PANEL, alpha))
    return Image.alpha_composite(image, overlay).convert("RGB")


def draw_sidebar(c: Canvas):
    c.line(SIDEBAR, 0, SIDEBAR, H, LINE_SOFT)

    # brand mark: four bars of 9/22/15/7px, centred in a 26px box
    bar_x = 24
    for height in (9, 22, 15, 7):
        top = 39 - height / 2
        c.rect(bar_x, top, bar_x + 4, top + height, 2, fill=ACCENT)
        bar_x += 7

    c.text(61, 25, "sotto", font("seguisb.ttf", 22), INK)
    c.track(61, 52, "SPEECH → NOTES", font("segoeui.ttf", 10.5), MUTED2, 1.5)

    # new note button (padding 11 14, border 1, radius 11)
    c.rect(18, 92, 278, 132, 11, fill=PANEL2, outline=LINE)
    label = "New note"
    icon_w, gap = 13, 8
    text_w = c.width(label, font("segoeui.ttf", 13.5))
    start_x = 148 - (icon_w + gap + text_w) / 2
    c.line(start_x + 6.5, 107, start_x + 6.5, 119, ACCENT, 1.6)
    c.line(start_x, 113, start_x + 13, 113, ACCENT, 1.6)
    c.text(start_x + icon_w + gap, 112, label, font("segoeui.ttf", 13.5), INK, anchor="lm")

    # library head
    c.track(26, 159, "LIBRARY", font("segoeui.ttf", 10.5), MUTED2, 1.5)
    c.rect(258, 154, 278, 170, 8, fill=PANEL2, outline=LINE_SOFT)
    c.text(268, 162, str(len(_NOTES)), font("consola.ttf", 10), MUTED, anchor="mm")

    y = 177
    for title, meta, active in _NOTES:
        if active:
            c.rect(18, y, 278, y + 56, 11, fill=PANEL2, outline=LINE)
        c.text(30, y + 10, title, font("seguisb.ttf", 13.5),
               ACCENT if active else INK)
        c.text(30, y + 31, meta, font("consola.ttf", 10), MUTED2)
        y += 60.2

    # footer sits on the sidebar's 18px bottom padding
    c.line(26, 867, 270, 867, LINE_SOFT)
    c.dot(34, 888, 6, (35, 48, 20))
    c.dot(34, 888, 3, ACCENT)
    c.text(46, 888, "local · 127.0.0.1", font("consola.ttf", 10.5), MUTED, anchor="lm")
    c.text(26, 902, "tiny · cpu · ready", font("segoeui.ttf", 11), MUTED2)


def draw_topbar(c: Canvas, title: str):
    c.line(0, 61, W, 61, LINE_SOFT)
    x = 330
    f = font("segoeui.ttf", 12.5)
    c.text(x, 30, "notebook", f, MUTED2, anchor="lm")
    x += c.width("notebook", f) + 7
    c.text(x, 30, "/", f, (51, 56, 69), anchor="lm")
    x += c.width("/", f) + 7
    c.text(x, 30, title, f, INK_DIM, anchor="lm")

    right = W - 34
    status_f = font("consola.ttf", 11.5)
    text_w = c.width("saved", status_f)
    c.dot(right - text_w - 12, 30.5, 2.5, ACCENT)
    c.text(right, 30, "saved", status_f, MUTED, anchor="rm")


def draw_note(c: Canvas):
    x = INNER_X
    c.track(x, 103, "Morning rehearsal — take 2", font("seguisb.ttf", 36), INK, -1.2)

    pills = [
        ("duration", "01:52"),
        ("language", "EN"),
        ("engine", "local · tiny"),
        ("segments", "6"),
        ("saved", "27 Nov 2026"),
    ]
    px, py = x, 159
    for label, value in pills:
        label_w = c.width(label + " ", font("consola.ttf", 10))
        value_w = c.width(value, font("consolab.ttf", 10))
        width = label_w + value_w + 16
        c.rect(px, py, px + width, py + 20, 5, fill=PANEL, outline=LINE_SOFT)
        c.text(px + 7, py + 10, label + " ", font("consola.ttf", 10), MUTED, anchor="lm")
        c.text(px + 7 + label_w, py + 10, value, font("consolab.ttf", 10), INK_DIM, anchor="lm")
        px += width + 7

    # actions
    ay = 197
    label = "EXPORT"
    c.track(x, ay + 11, label, font("consola.ttf", 9.5), MUTED2, 1.0)
    bx = x + sum(c.width(ch, font("consola.ttf", 9.5)) + 1.0 for ch in label) + 10
    labels = ["Markdown", "SRT", "Text"]
    widths = [13 + 7 + c.width(t, font("segoeui.ttf", 12.5)) + 26 for t in labels]
    group_w = sum(widths)
    c.rect(bx, ay, bx + group_w, ay + 33, 9, outline=LINE)
    cursor = bx
    for i, (text, width) in enumerate(zip(labels, widths)):
        if i:
            c.line(cursor, ay + 1, cursor, ay + 32, LINE)
        download_icon(c, cursor + 13, ay + 10, INK_DIM)
        c.text(cursor + 33, ay + 17, text, font("segoeui.ttf", 12.5), INK_DIM, anchor="lm")
        cursor += width

    delete_text = "Delete"
    dw = 13 + 7 + c.width(delete_text, font("segoeui.ttf", 12.5)) + 26
    dx = x + INNER_W - dw
    c.rect(dx, ay, dx + dw, ay + 33, 9, outline=LINE)
    trash_icon(c, dx + 13, ay + 10, INK_DIM)
    c.text(dx + 33, ay + 17, delete_text, font("segoeui.ttf", 12.5), INK_DIM, anchor="lm")

    # player: 13px padding, 38px play button, 14px gaps
    py = 252
    c.gradient_rect(x, py, x + INNER_W, py + 66, 15, PANEL2, PANEL)
    c.rect(x, py, x + INNER_W, py + 66, 15, outline=LINE)
    cx = x + 16 + 19
    c.dot(cx, py + 33, 19, ACCENT)
    play_icon(c, cx, py + 33)

    time_x = x + 16 + 38 + 14
    cur, dur = "0:48", "1:52"
    f_time = font("consola.ttf", 11.5)
    c.text(time_x, py + 33, cur, f_time, MUTED, anchor="lm")
    cur_w = c.width(cur, f_time)
    c.text(time_x + cur_w + 3, py + 33, "/", f_time, (58, 63, 75), anchor="lm")
    sep_w = c.width("/", f_time)
    c.text(time_x + cur_w + 6 + sep_w, py + 33, dur, f_time, MUTED, anchor="lm")
    time_w = cur_w + 6 + sep_w + c.width(dur, f_time)

    speed_label = "1x"
    speed_w = c.width(speed_label, font("consola.ttf", 10.5)) + 16
    speed_x = x + INNER_W - 16 - speed_w
    seek_x = time_x + time_w + 14
    seek_w = speed_x - 14 - seek_x
    c.rect(seek_x, py + 31.5, seek_x + seek_w, py + 34.5, 2, fill=(42, 47, 58))
    c.rect(seek_x, py + 31.5, seek_x + seek_w * 0.43, py + 34.5, 2, fill=ACCENT)
    c.dot(seek_x + seek_w * 0.43, py + 33, 4.5, INK)

    c.rect(speed_x, py + 22.5, speed_x + speed_w, py + 43.5, 7, outline=LINE)
    c.text(speed_x + speed_w / 2, py + 33, speed_label, font("consola.ttf", 10.5), MUTED, anchor="mm")

    # speakers (collapsed details)
    sy = 332
    c.rect(x, sy, x + INNER_W, sy + 40, 12, fill=(14, 16, 20), outline=LINE_SOFT)
    c.text(x + 16, sy + 20, "+", font("consola.ttf", 13), ACCENT, anchor="lm")
    c.track(x + 34, sy + 14, "SPEAKERS · MANUAL LABELS", font("segoeui.ttf", 11), MUTED2, 1.2)

    draw_timeline(c, x, 398)


def draw_timeline(c: Canvas, x: int, top: int):
    f_seg = font("segoeui.ttf", 15)
    f_stamp = font("consola.ttf", 10.5)
    f_speaker = font("consola.ttf", 9.5)

    # lay out first so the vertical rule can stop where the last card does
    layout = []
    y = top
    for stamp, speaker, text in _SEGMENTS:
        lines = c.wrap(text, f_seg, 748)
        body_h = 7 + 18 + len(lines) * 24.3 + 9 + 2
        layout.append((y, body_h, lines, stamp, speaker))
        y += body_h + 10

    line_x = x + 71
    last_body_bottom = layout[-1][0] + 5 + layout[-1][1]
    c.line(line_x, top + 10, line_x, last_body_bottom - 7, LINE)

    for index, (sy, body_h, lines, stamp, speaker) in enumerate(layout):
        active = index == 1
        body_top = sy + 5
        body_left = x + 86
        body_right = x + INNER_W

        c.text(x + 53, sy + 16, stamp, f_stamp, MUTED2, anchor="ra")

        if active:
            c.rect(body_left, body_top, body_right, body_top + body_h, 11,
                   fill=PANEL2, outline=(45, 51, 62))
            c.dot(line_x + 1, sy + 22.5, 6.5, (36, 49, 21))
            c.dot(line_x + 1, sy + 22.5, 3.5, ACCENT)
        else:
            c.dot(line_x + 1, sy + 22.5, 3.5, BG, outline=(58, 64, 76))

        # speaker chip, absolute at top 6 / right 8 inside the card
        pw = c.width(speaker, f_speaker) + 25
        pill_x = body_right - 8 - pw
        c.rect(pill_x, body_top + 6, pill_x + pw, body_top + 23, 9,
               fill=PANEL, outline=(62, 73, 44))
        c.text(pill_x + 7, body_top + 14.5, speaker, f_speaker, ACCENT, anchor="lm")
        c.line(pill_x + pw - 12, body_top + 13, pill_x + pw - 9, body_top + 16, MUTED, 1)
        c.line(pill_x + pw - 9, body_top + 16, pill_x + pw - 6, body_top + 13, MUTED, 1)

        text_y = body_top + 25
        for line in lines:
            c.text(body_left + 12, text_y, line, f_seg, INK if active else INK_DIM)
            text_y += 24.3

    c.text(INNER_X + INNER_W, H - 24, "UI preview · sample content",
           font("consola.ttf", 9.5), MUTED2, anchor="ra")


def main() -> None:
    image = glow_background()
    c = Canvas(image)
    draw_sidebar(c)
    draw_topbar(c, "Morning rehearsal — take 2")
    draw_note(c)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    final = image.resize((W * S // S, H * S // S), Image.LANCZOS).resize((W, H), Image.LANCZOS)
    final.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
