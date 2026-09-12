"""Suggest posting dates from an image's month attribute.

Rule: a photo from the current month is posted this month (starting
tomorrow); a photo from a later month waits for that month. A photo from a
*past* month is posted in the current window by default, or, with
``seasonal=True``, held until the next occurrence of its month. Posts in one
run are spread evenly across the window, and each platform gets its own
preferred hour.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .platforms import PLATFORMS


@dataclass(frozen=True)
class ScheduleConfig:
    timezone: str = "UTC"
    weekdays_only: bool = True
    seasonal: bool = False  # True -> photos from past months wait for next year's same month
    start_from: date | None = None  # override "today"; useful for tests and re-runs


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown TIMEZONE {name!r}; use an IANA name like Asia/Bangkok") from exc


def target_window(image_month: int, today: date, *, seasonal: bool = False) -> tuple[date, date]:
    """(first_candidate_day, last_day_of_month) for the posting window."""
    if not 1 <= image_month <= 12:
        raise ValueError(f"month must be 1-12, got {image_month}")
    if image_month < today.month and not seasonal:
        image_month = today.month  # post now rather than wait a year
    if image_month == today.month:
        year = today.year
        start = today + timedelta(days=1)
        if start.month != image_month:  # today is the last day of the month
            year += 1
            start = date(year, image_month, 1)
    elif image_month > today.month:
        year = today.year
        start = date(year, image_month, 1)
    else:
        year = today.year + 1
        start = date(year, image_month, 1)
    end = date(year, image_month, calendar.monthrange(year, image_month)[1])
    return start, end


def candidate_days(start: date, end: date, *, weekdays_only: bool) -> list[date]:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if weekdays_only:
        weekdays = [d for d in days if d.weekday() < 5]
        if weekdays:
            return weekdays
    return days


def suggest_post_date(image_month: int, position: int, total: int, cfg: ScheduleConfig) -> date:
    """Day for the ``position``-th of ``total`` posts sharing this window."""
    today = cfg.start_from or datetime.now(_tz(cfg.timezone)).date()
    start, end = target_window(image_month, today, seasonal=cfg.seasonal)
    days = candidate_days(start, end, weekdays_only=cfg.weekdays_only)
    if total <= 1 or len(days) == 1:
        return days[0]
    idx = round(position * (len(days) - 1) / (total - 1))
    return days[min(max(idx, 0), len(days) - 1)]


def platform_post_at(day: date, platform: str, cfg: ScheduleConfig) -> str:
    hour = PLATFORMS[platform].post_hour
    return datetime.combine(day, time(hour=hour), tzinfo=_tz(cfg.timezone)).isoformat()
