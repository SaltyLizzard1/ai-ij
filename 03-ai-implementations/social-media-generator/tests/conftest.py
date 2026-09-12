from __future__ import annotations

import csv
from pathlib import Path

import pytest
from PIL import Image

from social_pipeline.config import Settings
from social_pipeline.storage import Storage

SAMPLE_ARTICLE = Path(__file__).resolve().parents[1] / "examples" / "sample-article.md"


def make_library(root: Path, layout: dict[str, dict[str, float]]) -> tuple[Path, Path]:
    """Create ``root/X/<month>/<file>`` photos plus a blur2.csv under ``root/records``."""
    lib = root / "X"
    records = root / "records"
    records.mkdir(parents=True, exist_ok=True)
    rows = []
    for folder, files in layout.items():
        (lib / folder).mkdir(parents=True, exist_ok=True)
        for name, blur in files.items():
            Image.new("RGB", (120, 90), (180, 120, 60)).save(lib / folder / name)
            rows.append({"path": f"X:/{folder}\\{name}", "w": 4000, "h": 3000, "blur": blur, "lapvar": 300, "p99": 90, "contrast": 55, "error": ""})
    with (records / "blur2.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["path", "w", "h", "blur", "lapvar", "p99", "contrast", "error"])
        writer.writeheader()
        writer.writerows(rows)
    return lib, records


@pytest.fixture
def library(tmp_path: Path) -> tuple[Path, Path]:
    return make_library(
        tmp_path,
        {
            "2026-09": {"IMG_scooter.jpg": 0.30, "IMG_market.jpg": 0.25, "IMG_blurry.jpg": 0.90},
            "2026-08": {"IMG_mountain.jpg": 0.20},
            "blurred": {"IMG_bad.jpg": 0.95},
        },
    )


@pytest.fixture
def settings(library: tuple[Path, Path], tmp_path: Path) -> Settings:
    lib, records = library
    s = Settings(
        llm_provider="mock",
        image_root=str(lib),
        records_dir=str(records),
        db_path=str(tmp_path / "test.db"),
        output_dir=str(tmp_path / "out"),
        platforms=("linkedin", "x", "instagram", "facebook"),
        timezone="Asia/Bangkok",
        llm_max_retries=2,
    )
    s.validate()
    return s


@pytest.fixture
def storage(settings: Settings):
    with Storage(settings.db_path) as st:
        yield st
