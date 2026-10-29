"""Render the fictional sample documents (src/sim/documents.py) to PNGs that the
reader agent can read with Muse Spark vision.

    python scripts/make_sample_docs.py      # writes src/api/static/samples/*.png and data/reader_eval/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.sim.documents import FOOTER, SAMPLES, eval_documents  # noqa: E402

OUT = ROOT / "src" / "api" / "static" / "samples"
EVAL_OUT = ROOT / "data" / "reader_eval"
FONTS = Path("/usr/share/fonts/truetype/dejavu")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


STYLE = {"h1": (font("DejaVuSerif-Bold.ttf", 30), 46), "b": (font("DejaVuSans-Bold.ttf", 19), 32),
         "small": (font("DejaVuSans.ttf", 14), 24), "": (font("DejaVuSans.ttf", 18), 28),
         "mono": (font("DejaVuSansMono.ttf", 17), 27), "rule": (None, 18)}


def render(kind: str) -> Path:
    return render_doc(SAMPLES[kind], OUT)


def render_doc(s: dict, out: Path) -> Path:
    w = 1100
    h = 80 + sum(STYLE[k][1] for k, _ in s["lines"]) + 90
    img = Image.new("RGB", (w, h), (252, 251, 247))
    d = ImageDraw.Draw(img)
    y = 50
    for k, text in s["lines"]:
        f, lh = STYLE[k]
        if k == "rule":
            d.line([(60, y + 6), (w - 60, y + 6)], fill=(60, 60, 60), width=2)
        elif text:
            d.text((60, y), text, font=f, fill=(25, 25, 25))
        y += lh
    d.rectangle([(40, h - 62), (w - 40, h - 26)], outline=(170, 40, 40), width=2)
    d.text((56, h - 54), FOOTER, font=font("DejaVuSans-Bold.ttf", 14), fill=(170, 40, 40))
    out.mkdir(parents=True, exist_ok=True)
    path = out / s["file"]
    img.save(path, optimize=True)
    return path


if __name__ == "__main__":
    for k in SAMPLES:
        print(render(k))
    docs = eval_documents()
    for d in docs:
        render_doc(d, EVAL_OUT)
    print(f"{len(docs)} eval documents -> {EVAL_OUT.relative_to(ROOT)}")
