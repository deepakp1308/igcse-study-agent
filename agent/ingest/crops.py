"""Crop figure regions from rendered page PNGs using normalized bboxes."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from agent.store.schemas import BoundingBox


def crop_bboxes_to_files(
    page_png: Path,
    bboxes: list[BoundingBox],
    out_dir: Path,
    basename: str,
) -> list[Path]:
    """Crop each bbox from ``page_png`` and save to ``out_dir`` as PNG.

    Returns crop paths in the same order as ``bboxes``. Paths are stable so
    re-running is cheap.
    """

    if not bboxes:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    crops: list[Path] = []
    with Image.open(page_png) as opened:
        rgb = opened.convert("RGB")
        w, h = rgb.size
        for i, bb in enumerate(bboxes):
            left = max(0, int(bb.x * w))
            top = max(0, int(bb.y * h))
            right = min(w, int((bb.x + bb.w) * w))
            bottom = min(h, int((bb.y + bb.h) * h))
            if right - left <= 0 or bottom - top <= 0:
                continue
            crop = rgb.crop((left, top, right, bottom))
            out = out_dir / f"{basename}-fig{i:02d}.png"
            crop.save(out, "PNG", optimize=True)
            crops.append(out)
    return crops
