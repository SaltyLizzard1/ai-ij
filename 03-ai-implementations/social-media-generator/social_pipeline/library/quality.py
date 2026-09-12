"""Compute the same quality columns as ``blur2.csv`` for new photos.

Columns: ``path, w, h, blur, lapvar, p99, contrast, error``

* ``blur``     Crete-Roffet perceptual blur metric, 0 (sharp) .. 1 (blurred).
               Same definition as ``skimage.measure.blur_effect`` (h_size=11),
               implemented here with numpy only.
* ``lapvar``   Variance of the Laplacian (classic focus measure).
* ``p99``      99th percentile of the absolute Laplacian.
* ``contrast`` Standard deviation of the grayscale image.

Scores are written back to ``blur2.csv`` in the same path format the original
scorer used (``X:/2026-09\\name.jpg``) so both tools stay interchangeable.
"""

from __future__ import annotations

import csv
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..errors import ImageIndexError
from ..models import PHOTO_EXTENSIONS

log = logging.getLogger(__name__)

CSV_FIELDS = ["path", "w", "h", "blur", "lapvar", "p99", "contrast", "error"]


@dataclass(frozen=True)
class QualityScore:
    path: str  # in blur2.csv format
    width: int
    height: int
    blur: float
    lapvar: float
    p99: float
    contrast: float

    def to_row(self) -> dict[str, object]:
        return {
            "path": self.path, "w": self.width, "h": self.height, "blur": self.blur,
            "lapvar": self.lapvar, "p99": self.p99, "contrast": self.contrast, "error": "",
        }


def _load_gray(path: Path) -> np.ndarray:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover
        raise ImageIndexError("Pillow is required for scoring") from exc
    if path.suffix.lower() == ".heic":
        try:
            import pillow_heif  # type: ignore

            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise ImageIndexError(f"{path.name}: HEIC needs 'pillow-heif'") from exc
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            gray = np.asarray(im.convert("L"), dtype=np.float64)
    except OSError as exc:
        raise ImageIndexError(f"Could not decode {path.name}: {exc}") from exc
    if gray.ndim != 2 or min(gray.shape) < 16:
        raise ImageIndexError(f"{path.name}: image too small to score")
    return gray


def _uniform_filter1d(a: np.ndarray, size: int, axis: int) -> np.ndarray:
    """Moving average along ``axis`` with reflect padding (as scipy.ndimage does)."""
    half = size // 2
    pad = [(0, 0)] * a.ndim
    pad[axis] = (half, size - 1 - half)
    padded = np.pad(a, pad, mode="reflect")
    cs = np.cumsum(padded, axis=axis, dtype=np.float64)
    cs = np.concatenate([np.zeros_like(np.take(cs, [0], axis=axis)), cs], axis=axis)
    n = a.shape[axis]
    upper = np.take(cs, np.arange(size, size + n), axis=axis)
    lower = np.take(cs, np.arange(0, n), axis=axis)
    return (upper - lower) / size


def _sobel_axis(a: np.ndarray, axis: int) -> np.ndarray:
    """Sobel derivative along ``axis`` (smoothing across the other), reflect padded."""
    other = 1 - axis
    p = np.pad(a, 1, mode="reflect")
    # smooth [1,2,1] across the other axis
    if other == 0:
        s = p[:-2, :] + 2 * p[1:-1, :] + p[2:, :]
    else:
        s = p[:, :-2] + 2 * p[:, 1:-1] + p[:, 2:]
    # derivative [1,0,-1] along axis
    if axis == 0:
        d = s[2:, 1:-1] - s[:-2, 1:-1]
    else:
        d = s[1:-1, 2:] - s[1:-1, :-2]
    return d / 8.0


def blur_effect(gray: np.ndarray, h_size: int = 11) -> float:
    """Crete-Roffet perceptual blur: 0 sharp .. 1 blurred (max over axes)."""
    shape = gray.shape
    slices = tuple(slice(2, s - 1) for s in shape)
    scores = []
    for ax in range(gray.ndim):
        filt = _uniform_filter1d(gray, h_size, axis=ax)
        im_sharp = np.abs(_sobel_axis(gray, ax))
        im_blur = np.abs(_sobel_axis(filt, ax))
        t = np.maximum(0.0, im_sharp - im_blur)
        m1 = float(np.sum(im_sharp[slices]))
        m2 = float(np.sum(t[slices]))
        scores.append(abs(m1 - m2) / m1 if m1 > 0 else 1.0)
    return float(max(scores))


def laplacian(gray: np.ndarray) -> np.ndarray:
    p = np.pad(gray, 1, mode="reflect")
    return p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * p[1:-1, 1:-1]


def score_image(path: Path, *, record_path: str) -> QualityScore:
    gray = _load_gray(path)
    lap = laplacian(gray)
    return QualityScore(
        path=record_path,
        width=int(gray.shape[1]),
        height=int(gray.shape[0]),
        blur=round(blur_effect(gray), 6),
        lapvar=round(float(lap.var()), 4),
        p99=round(float(np.percentile(np.abs(lap), 99)), 2),
        contrast=round(float(gray.std()), 4),
    )


def record_path_for(image_root: Path, rel_path: str) -> str:
    """``X:\\`` + ``2026-09/name.jpg`` -> ``X:/2026-09\\name.jpg`` (original scorer's format)."""
    root = str(image_root).replace("\\", "/").rstrip("/")
    parts = rel_path.split("/")
    return f"{root}/{'/'.join(parts[:-1])}\\{parts[-1]}"


def existing_keys(csv_path: Path) -> set[str]:
    from .scanner import _record_key

    if not csv_path.is_file():
        return set()
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        return {_record_key(row["path"]) for row in csv.DictReader(fh) if row.get("path")}


def append_scores(csv_path: Path, scores: list[QualityScore], *, backup: bool = True) -> int:
    """Append rows to blur2.csv (creating it with a header if needed)."""
    if not scores:
        return 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.is_file()
    if backup and not new_file:
        shutil.copy2(csv_path, csv_path.with_suffix(csv_path.suffix + ".bak"))
    try:
        with csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            if new_file:
                writer.writeheader()
            for s in scores:
                writer.writerow(s.to_row())
    except OSError as exc:
        raise ImageIndexError(f"Could not write {csv_path}: {exc}") from exc
    return len(scores)


def unscored_photos(image_root: Path, csv_path: Path, *, months: set[str] | None, skip_folders: tuple[str, ...]) -> list[tuple[Path, str]]:
    """(absolute_path, relative_posix_path) for photos with no row in blur2.csv."""
    from .scanner import LibraryScanner, _record_key

    have = existing_keys(csv_path)
    scanner = LibraryScanner(image_root, records_dir=None, skip_folders=skip_folders, read_dimensions=False)
    out = []
    for folder in scanner.month_folders():
        if months and folder.name not in months:
            continue
        for file in sorted(folder.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in PHOTO_EXTENSIONS:
                continue
            rel = file.relative_to(image_root).as_posix()
            if any(part.lower() in scanner.skip for part in Path(rel).parts[:-1]):
                continue
            if _record_key(rel) not in have:
                out.append((file, rel))
    return out
