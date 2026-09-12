"""Scan the camera roll (``X:\\`` with ``YYYY-MM`` folders) into ImageAssets.

Pictures are not labelled, so the only metadata available at scan time is:

* month / year        - from the folder name (your Sort-CameraRoll.ps1 layout)
* width, height       - from ``blur2.csv`` if present, else read from the file
* blur, contrast, p99 - from ``blur2.csv`` (your existing quality scoring)

Semantic tags (subject, mood, themes) are added later by the vision tagger.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..errors import ImageIndexError
from ..models import PHOTO_EXTENSIONS, ImageAsset, stable_id

log = logging.getLogger(__name__)

MONTH_FOLDER = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class QualityRecord:
    width: int | None
    height: int | None
    blur: float | None
    contrast: float | None
    brightness: float | None


def _record_key(path_like: str) -> str:
    """``X:/2026-03\\20260311_102047.jpg`` -> ``2026-03/20260311_102047.jpg``.

    Keyed on the last two components so it matches regardless of drive letter
    or whether the CSV was produced from a mirrored or streamed Drive path.
    """
    parts = [p for p in re.split(r"[\\/]+", path_like.strip()) if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}".lower()
    return parts[-1].lower() if parts else ""


def _to_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def load_quality_records(records_dir: str | Path | None, *, filename: str = "blur2.csv") -> dict[str, QualityRecord]:
    """Read ``blur2.csv`` (path,w,h,blur,lapvar,p99,contrast,error) into a lookup."""
    if not records_dir:
        return {}
    csv_path = Path(records_dir) / filename
    if not csv_path.is_file():
        log.warning("Quality records not found at %s; continuing without blur scores", csv_path)
        return {}
    records: dict[str, QualityRecord] = {}
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            required = {"path", "blur"}
            if not reader.fieldnames or not required.issubset({f.strip() for f in reader.fieldnames}):
                raise ImageIndexError(f"{csv_path} is missing required columns {sorted(required)}")
            for row in reader:
                if (row.get("error") or "").strip():
                    continue  # scorer failed on this file; treat as unscored
                key = _record_key(row["path"])
                if not key:
                    continue
                records[key] = QualityRecord(
                    width=_to_int(row.get("w")),
                    height=_to_int(row.get("h")),
                    blur=_to_float(row.get("blur")),
                    contrast=_to_float(row.get("contrast")),
                    brightness=_to_float(row.get("p99")),
                )
    except OSError as exc:
        raise ImageIndexError(f"Could not read {csv_path}: {exc}") from exc
    log.info("Loaded %d quality records from %s", len(records), csv_path)
    return records


def _read_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image  # lazy: Pillow is only needed without records

        with Image.open(path) as im:
            return im.width, im.height
    except Exception:  # noqa: BLE001 - dimensions are a nice-to-have
        return None, None


class LibraryScanner:
    """Walk ``image_root`` and yield an :class:`ImageAsset` per photo."""

    def __init__(
        self,
        image_root: str | Path,
        *,
        records_dir: str | Path | None = None,
        skip_folders: tuple[str, ...] = ("blurred",),
        read_dimensions: bool = True,
    ) -> None:
        self.root = Path(image_root)
        self.records_dir = Path(records_dir) if records_dir else None
        self.skip = {s.lower() for s in skip_folders}
        self.read_dimensions = read_dimensions

    def month_folders(self) -> list[Path]:
        if not self.root.is_dir():
            raise ImageIndexError(
                f"Image root not reachable: {self.root} (is Google Drive running / the drive mounted?)"
            )
        folders = [p for p in self.root.iterdir() if p.is_dir() and MONTH_FOLDER.match(p.name)]
        return sorted(folders)

    def scan(self, *, months: set[str] | None = None) -> list[ImageAsset]:
        """Return assets for every photo in the month folders.

        ``months`` limits the scan to folder names like ``{"2026-09"}``.
        """
        records = load_quality_records(self.records_dir)
        assets: list[ImageAsset] = []
        now = datetime.now(timezone.utc)
        for folder in self.month_folders():
            if months and folder.name not in months:
                continue
            m = MONTH_FOLDER.match(folder.name)
            assert m is not None
            year, month = int(m.group(1)), int(m.group(2))
            for file in sorted(folder.rglob("*")):
                if not file.is_file() or file.suffix.lower() not in PHOTO_EXTENSIONS:
                    continue
                if any(part.lower() in self.skip for part in file.relative_to(self.root).parts[:-1]):
                    continue
                rel = file.relative_to(self.root).as_posix()
                rec = records.get(_record_key(rel))
                width = height = None
                blur = contrast = brightness = None
                source = "none"
                if rec:
                    width, height = rec.width, rec.height
                    blur, contrast, brightness = rec.blur, rec.contrast, rec.brightness
                    source = "records"
                if (width is None or height is None) and self.read_dimensions:
                    width, height = _read_dimensions(file)
                assets.append(
                    ImageAsset(
                        id=stable_id(rel.lower()),
                        path=rel,
                        file_name=file.name,
                        month=month,
                        year=year,
                        width=width,
                        height=height,
                        blur=blur,
                        contrast=contrast,
                        brightness=brightness,
                        quality_source=source,
                    )
                )
        log.info("Scanned %d photos under %s (%s)", len(assets), self.root, now.date())
        return assets

    def absolute_path(self, asset: ImageAsset) -> Path:
        return self.root / Path(asset.path)
