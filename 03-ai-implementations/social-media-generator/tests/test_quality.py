import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from social_pipeline.library.quality import (
    append_scores,
    blur_effect,
    existing_keys,
    record_path_for,
    score_image,
    unscored_photos,
)


def _noisy_image(path: Path, blur_radius: float = 0.0) -> None:
    rng = np.random.default_rng(1)
    arr = (rng.random((240, 320)) * 255).astype("uint8")
    im = Image.fromarray(arr, mode="L").convert("RGB")
    if blur_radius:
        im = im.filter(ImageFilter.GaussianBlur(blur_radius))
    im.save(path, quality=95)


def test_blur_effect_orders_sharp_before_blurred(tmp_path):
    sharp, soft = tmp_path / "sharp.jpg", tmp_path / "soft.jpg"
    _noisy_image(sharp)
    _noisy_image(soft, blur_radius=3.0)
    s1 = score_image(sharp, record_path="x")
    s2 = score_image(soft, record_path="y")
    assert 0.0 <= s1.blur < s2.blur <= 1.0
    assert s1.lapvar > s2.lapvar and s1.p99 > s2.p99
    assert s1.width == 320 and s1.height == 240


def test_blur_effect_is_scale_invariant():
    rng = np.random.default_rng(2)
    a = rng.random((64, 80)) * 255
    assert abs(blur_effect(a) - blur_effect(a / 255.0)) < 1e-9


def test_record_path_matches_original_scorer_format():
    assert record_path_for(Path("X:\\"), "2026-09/IMG.jpg") == "X:/2026-09\\IMG.jpg"
    assert record_path_for(Path("/mnt/x"), "2026-09/IMG.jpg") == "/mnt/x/2026-09\\IMG.jpg"


def test_unscored_then_append_then_scanner_sees_them(tmp_path):
    from social_pipeline.library.scanner import LibraryScanner
    from tests.conftest import make_library

    lib, records = make_library(tmp_path, {"2026-09": {"old.jpg": 0.3}})
    _noisy_image(lib / "2026-09" / "new.jpg")
    csv_path = records / "blur2.csv"
    todo = unscored_photos(lib, csv_path, months=None, skip_folders=("blurred",))
    assert [rel for _, rel in todo] == ["2026-09/new.jpg"]

    scores = [score_image(f, record_path=record_path_for(lib, rel)) for f, rel in todo]
    assert append_scores(csv_path, scores) == 1
    assert (records / "blur2.csv.bak").is_file()
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    assert len(rows) == 2 and rows[-1]["error"] == ""
    assert "2026-09/new.jpg" in existing_keys(csv_path)
    assert unscored_photos(lib, csv_path, months=None, skip_folders=("blurred",)) == []

    new = next(a for a in LibraryScanner(lib, records_dir=records).scan() if a.file_name == "new.jpg")
    assert new.quality_source == "records" and new.blur is not None and new.width == 320
