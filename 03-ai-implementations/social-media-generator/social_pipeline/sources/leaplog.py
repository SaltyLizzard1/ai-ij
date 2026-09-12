"""The Leap Log on quityourlifeandtravel.com as an article source.

The site lists posts from two places (see ``components/LeapLog.tsx`` in the
qylat-next repo): Sanity CMS posts served by the site's own ``/api/posts``
route, plus a hardcoded post in ``data/posts.tsx``. The order on the page is
the pinned post first, then newest first. This module reproduces that list
and turns a post into an :class:`Article`:

* Sanity posts: Portable Text body -> Markdown (clean, no page chrome).
* Hardcoded posts: fetch the rendered ``/leap/<slug>`` page as HTML.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..articles import USER_AGENT, fetch_url
from ..errors import ArticleLoadError
from ..models import Article

log = logging.getLogger(__name__)

SANITY_LIST_QUERY = (
    '*[_type == "post" && defined(slug.current)] | order(publishedAt desc) '
    '{_id, title, "slug": slug.current, postType, excerpt, body, publishedAt, tags, '
    '"heroImageUrl": heroImage.asset->url}'
)


@dataclass
class LeapLogArticle:
    slug: str
    title: str
    url: str
    published_at: str | None = None  # ISO date/datetime
    excerpt: str = ""
    post_type: str = "blog"
    tags: list[str] = field(default_factory=list)
    source: str = "sanity"  # "sanity" | "site"
    pinned: bool = False
    hero_image_url: str | None = None
    body: list[dict[str, Any]] | None = None  # Portable Text, when known

    @property
    def published_date(self) -> str | None:
        return self.published_at[:10] if self.published_at else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug, "title": self.title, "url": self.url, "published_at": self.published_at,
            "published_date": self.published_date, "excerpt": self.excerpt, "post_type": self.post_type,
            "tags": list(self.tags), "source": self.source, "pinned": self.pinned, "hero_image_url": self.hero_image_url,
        }


# --------------------------------------------------------------- portable text
def _span_text(child: dict[str, Any], mark_defs: dict[str, dict[str, Any]]) -> str:
    text = str(child.get("text", ""))
    if not text:
        return ""
    for mark in child.get("marks", []) or []:
        if mark == "strong":
            text = f"**{text}**"
        elif mark == "em":
            text = f"*{text}*"
        elif mark == "code":
            text = f"`{text}`"
        elif mark in mark_defs and mark_defs[mark].get("_type") == "link" and mark_defs[mark].get("href"):
            text = f"[{text}]({mark_defs[mark]['href']})"
    return text


def portable_text_to_markdown(blocks: list[dict[str, Any]] | None) -> str:
    """Convert Sanity Portable Text to Markdown. Unknown block types are skipped."""
    out: list[str] = []
    list_buffer: list[str] = []
    numbered = 0

    def flush_list() -> None:
        nonlocal numbered
        if list_buffer:
            out.append("\n".join(list_buffer))
            list_buffer.clear()
        numbered = 0

    for block in blocks or []:
        btype = block.get("_type")
        if btype == "block":
            mark_defs = {m["_key"]: m for m in block.get("markDefs", []) or [] if m.get("_key")}
            text = "".join(_span_text(c, mark_defs) for c in block.get("children", []) or []).strip()
            if not text:
                continue
            style = block.get("style", "normal") or "normal"
            if block.get("listItem"):
                if block["listItem"] == "number":
                    numbered += 1
                    list_buffer.append(f"{numbered}. {text}")
                else:
                    list_buffer.append(f"- {text}")
                continue
            flush_list()
            if style.startswith("h") and style[1:].isdigit():
                out.append("#" * min(int(style[1:]), 6) + " " + text)
            elif style == "blockquote":
                out.append("> " + text)
            else:
                out.append(text)
        elif btype == "image":
            flush_list()
            caption = block.get("caption") or block.get("alt") or ""
            if caption:
                out.append(f"*[Photo: {caption}]*")
        else:
            flush_list()  # code, embeds, CTAs: not post text
    flush_list()
    return "\n\n".join(out).strip() + ("\n" if out else "")


# ---------------------------------------------------------------------- client
class LeapLogClient:
    def __init__(
        self,
        *,
        site_base_url: str = "https://www.quityourlifeandtravel.com",
        sanity_project_id: str | None = "zvvdrylu",
        sanity_dataset: str = "production",
        pinned_slug: str | None = "how-to-move-to-thailand-in-60-days",
        extra_slugs: tuple[str, ...] = ("how-to-move-to-thailand-in-60-days",),
        fetch_json: Callable[[str], Any] | None = None,
        fetch_text: Callable[[str], str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.site = site_base_url.rstrip("/")
        self.project = sanity_project_id
        self.dataset = sanity_dataset
        self.pinned = pinned_slug
        self.extra_slugs = tuple(extra_slugs)
        self.timeout = timeout
        self._fetch_json = fetch_json or self._default_fetch_json
        self._fetch_text = fetch_text or (lambda url: fetch_url(url, timeout=timeout))

    # --- http
    def _default_fetch_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ArticleLoadError(f"HTTP {exc.code} fetching {url}", retryable=exc.code >= 500) from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ArticleLoadError(f"Could not fetch {url}: {exc}", retryable=True) from exc

    def post_url(self, slug: str) -> str:
        return f"{self.site}/leap/{slug}"

    # --- listing
    def _sanity_posts(self) -> list[dict[str, Any]]:
        """Site route first (what the page uses), Sanity CDN as a fallback."""
        try:
            data = self._fetch_json(f"{self.site}/api/posts")
            if isinstance(data, list):
                return data
        except ArticleLoadError as exc:
            log.warning("Site /api/posts failed (%s); trying the Sanity CDN", exc)
        if not self.project:
            return []
        url = (
            f"https://{self.project}.apicdn.sanity.io/v2024-01-01/data/query/{self.dataset}?"
            + urllib.parse.urlencode({"query": SANITY_LIST_QUERY})
        )
        data = self._fetch_json(url)
        result = data.get("result") if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def list_articles(self) -> list[LeapLogArticle]:
        articles: dict[str, LeapLogArticle] = {}
        for p in self._sanity_posts():
            slug = p.get("slug")
            if not slug:
                continue
            articles[slug] = LeapLogArticle(
                slug=slug, title=p.get("title") or slug, url=self.post_url(slug), published_at=p.get("publishedAt"),
                excerpt=p.get("excerpt") or "", post_type=p.get("postType") or "blog", tags=list(p.get("tags") or []),
                source="sanity", hero_image_url=p.get("heroImageUrl"), body=p.get("body") if isinstance(p.get("body"), list) else None,
            )
        for slug in self.extra_slugs:
            if slug not in articles:
                articles[slug] = LeapLogArticle(
                    slug=slug, title=slug.replace("-", " ").title(), url=self.post_url(slug), source="site",
                    published_at=HARDCODED_DATES.get(slug),
                )
        for a in articles.values():
            a.pinned = a.slug == self.pinned

        def sort_key(a: LeapLogArticle) -> tuple[int, float]:
            ts = 0.0
            if a.published_at:
                try:
                    ts = datetime.fromisoformat(a.published_at.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    ts = 0.0
            return (0 if a.pinned else 1, -ts)

        return sorted(articles.values(), key=sort_key)

    # --- fetching one post
    def fetch_article(self, slug: str) -> Article:
        listing = {a.slug: a for a in self.list_articles()}
        meta = listing.get(slug)
        if meta is None:
            raise ArticleLoadError(f"No Leap Log post with slug {slug!r}")
        url = self.post_url(slug)
        if meta.body:
            markdown = portable_text_to_markdown(meta.body)
            if markdown.strip():
                header = f"# {meta.title}\n\n"
                return Article.create(header + markdown, title=meta.title, source_format="markdown", source_url=url)
        html = self._fetch_text(url)
        if not html.strip():
            raise ArticleLoadError(f"Empty page for {url}")
        title = meta.title if meta.source == "sanity" else _title_from_html(html) or meta.title
        return Article.create(html, title=title, source_format="html", source_url=url)


HARDCODED_DATES = {"how-to-move-to-thailand-in-60-days": "2026-03-15"}


def _title_from_html(html: str) -> str | None:
    from ..articles import extract_title

    title = extract_title(html, "html")
    if title and "|" in title:
        title = title.split("|")[0].strip()
    return title
