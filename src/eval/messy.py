"""Messy-photo augmentation for the reader eval: what a phone photo of a letter
on a kitchen table looks like. Deterministic per (document, level)."""
from __future__ import annotations

import base64
import io
import random

from PIL import Image, ImageEnhance, ImageFilter

LEVELS = ["clean", "phone", "messy", "harsh"]


def messy(img: Image.Image, level: str, seed: str) -> Image.Image:
    if level == "clean":
        return img
    rng = random.Random(f"{seed}:{level}")
    cfg = {"phone": (2.0, 0.6, 0.9, 70, 0.0, 0), "messy": (-4.5, 1.1, 0.72, 40, 0.025, 0), "harsh": (7.0, 1.6, 0.55, 18, 0.045, 14)}[level]
    angle, blur, light, quality, crop, noise = cfg
    img = img.convert("RGB").rotate(angle + rng.uniform(-0.5, 0.5), resample=Image.BICUBIC, expand=True, fillcolor=(60, 58, 55))
    if crop:
        w, h = img.size
        img = img.crop((int(w * crop), int(h * crop), int(w * (1 - crop)), int(h * (1 - crop))))
    img = img.filter(ImageFilter.GaussianBlur(blur))
    img = ImageEnhance.Brightness(img).enhance(light)
    if level == "harsh":
        img = ImageEnhance.Contrast(img).enhance(0.8)
    if noise:
        px = img.load()
        w, h = img.size
        for _ in range(w * h // 9):
            x, y = rng.randrange(w), rng.randrange(h)
            r, g, b = px[x, y]
            n = rng.randint(-noise, noise)
            px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    if img.format == "JPEG":
        img.save(buf, "JPEG", quality=95)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
