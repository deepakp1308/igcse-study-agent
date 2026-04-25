"""Figure cropping unit tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from agent.ingest.crops import crop_bboxes_to_files
from agent.store.schemas import BoundingBox


def test_crop_single_bbox(tmp_path: Path):
    src = tmp_path / "page.png"
    img = Image.new("RGB", (1000, 2000), color=(200, 200, 200))
    img.save(src)
    crops = crop_bboxes_to_files(
        src,
        [BoundingBox(x=0.1, y=0.1, w=0.5, h=0.5)],
        tmp_path / "out",
        basename="q00",
    )
    assert len(crops) == 1
    assert crops[0].exists()
    with Image.open(crops[0]) as c:
        assert c.size == (500, 1000)


def test_crop_clamps_to_bounds(tmp_path: Path):
    src = tmp_path / "page.png"
    Image.new("RGB", (100, 100)).save(src)
    crops = crop_bboxes_to_files(
        src,
        [BoundingBox(x=0.9, y=0.9, w=0.5, h=0.5)],
        tmp_path / "out",
        basename="q00",
    )
    assert len(crops) == 1
    with Image.open(crops[0]) as c:
        assert c.size == (10, 10)


def test_crop_no_bboxes_returns_empty(tmp_path: Path):
    src = tmp_path / "page.png"
    Image.new("RGB", (100, 100)).save(src)
    assert crop_bboxes_to_files(src, [], tmp_path / "out", "q00") == []
