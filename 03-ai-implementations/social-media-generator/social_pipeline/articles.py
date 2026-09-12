"""Load a long-form article from a URL, a file, or raw text."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

from .errors import ArticleLoadError
from .models import Article

USER_AGENT = "social-pipeline/0.1 (+https://github.com/SaltyLizzard1/ai-ij)"
_HTML_MARKERS = re.compile(
    r"<(html|body|article|main|div|p|h[1-6]|ul|ol|section|br)[\s>/]", re.IGNORECASE
)


def detect_format(text: str) -> str:
    """Return "html" if the text looks like markup, otherwise "markdown"."""
    head = text.lstrip()[:4000]
    return "html" if _HTML_MARKERS.search(head) else "markdown"


def extract_title(text: str, fmt: str) -> str | None:
    if fmt == "html":
        soup = BeautifulSoup(text, "html.parser")
        for selector in ("article h1", "main h1", "h1", "title"):
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                return node.get_text(" ", strip=True)
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            return str(og["content"]).strip()
        return None
    m = re.search(r"^\s*#\s+(.+?)\s*$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # Setext-style "Title\n=====" headings
    m = re.search(r"^(.+)\n=+\s*$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def fetch_url(url: str, *, timeout: float = 30.0) -> str:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise ArticleLoadError(f"Only http(s) URLs are supported: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise ArticleLoadError(
            f"HTTP {exc.code} fetching {url}", retryable=exc.code in (408, 429) or exc.code >= 500
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ArticleLoadError(f"Network error fetching {url}: {exc}", retryable=True) from exc
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def load_article(
    *,
    url: str | None = None,
    path: str | None = None,
    text: str | None = None,
    title: str | None = None,
    source_format: str | None = None,
) -> Article:
    """Build an :class:`Article` from exactly one of url / path / text."""
    given = [x for x in (url, path, text) if x]
    if len(given) != 1:
        raise ArticleLoadError("Provide exactly one of url, path or text")

    if url:
        raw = fetch_url(url)
        source_url: str | None = url
    elif path:
        p = Path(path)
        if not p.is_file():
            raise ArticleLoadError(f"Article file not found: {p}")
        try:
            raw = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ArticleLoadError(f"Article file is not UTF-8 text: {p}") from exc
        source_url = None
        if source_format is None and p.suffix.lower() in {".md", ".markdown", ".txt"}:
            source_format = "markdown"
        elif source_format is None and p.suffix.lower() in {".html", ".htm"}:
            source_format = "html"
    else:
        raw = text or ""
        source_url = None

    if not raw.strip():
        raise ArticleLoadError("Article content is empty")

    fmt = source_format or detect_format(raw)
    if fmt not in ("html", "markdown"):
        raise ArticleLoadError(f"Unsupported source_format {fmt!r}")

    resolved_title = title or extract_title(raw, fmt) or (Path(path).stem if path else "Untitled")
    return Article.create(raw, title=resolved_title, source_format=fmt, source_url=source_url)
