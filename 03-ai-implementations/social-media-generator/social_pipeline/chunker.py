"""Split an article (HTML or Markdown) into post-sized chunks.

Strategy
--------
1. Normalise everything to HTML (Markdown is rendered with python-markdown),
   strip navigation/boilerplate, and walk headings, paragraphs, lists and
   blockquotes in document order.
2. Group paragraphs under their nearest heading into *sections*, then pack
   each section's paragraphs into chunks between ``min_chars`` and
   ``max_chars``. Long paragraphs are split on sentence boundaries.
3. Bullet lists become their own "list" chunks (they post well as-is).
4. Blockquotes become "quote" chunks.
5. Punchy standalone sentences (numbers, questions, second person,
   imperatives, contrast words) are extracted as "hook" chunks with the
   surrounding paragraph attached as context.
6. Every chunk gets a ``post_score`` so the pipeline can pick the best N.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import markdown
from bs4 import BeautifulSoup, Tag

from .errors import ChunkingError
from .models import Chunk

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'“(A-Z0-9])")
_WS = re.compile(r"\s+")
_HOOK_IMPERATIVES = {
    "stop", "start", "don't", "dont", "never", "always", "try", "remember", "ask",
    "build", "write", "focus", "choose", "learn", "imagine", "think", "forget",
    "pick", "keep", "give", "take", "make", "notice", "here's", "heres",
}
_CONTRAST_WORDS = {"but", "instead", "however", "actually", "turns out", "except", "until", "unless"}
_WEAK_STARTS = {"this", "that", "it", "these", "those", "he", "she", "they", "which", "and", "or", "so"}
_BOILERPLATE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "iframe", "svg", "button"]
_BOILERPLATE_CLASSES = re.compile(r"(nav|menu|sidebar|footer|comment|share|social|related|breadcrumb|cookie|subscribe|newsletter)", re.I)


@dataclass
class _Block:
    kind: str  # heading | paragraph | list | quote
    text: str
    level: int = 0  # heading level


@dataclass
class _Section:
    heading: str | None
    blocks: list[_Block] = field(default_factory=list)


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def _to_root(text: str, fmt: str) -> Tag:
    html = markdown.markdown(text, extensions=["extra", "sane_lists"]) if fmt == "markdown" else text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_BOILERPLATE_TAGS):
        tag.decompose()
    for tag in soup.find_all(True, attrs={"class": _BOILERPLATE_CLASSES}):
        # Only strip containers, never a whole <article>/<main>.
        if tag.name not in ("article", "main", "body", "html"):
            tag.decompose()
    # Tailwind's `not-prose` marks CTAs, forms and widgets inside a post; keep quotes.
    for tag in soup.find_all(True, class_="not-prose"):
        if tag.name not in ("blockquote", "article", "main", "body", "html") and tag.find("blockquote") is None:
            tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    return root


def _extract_blocks(root: Tag) -> list[_Block]:
    blocks: list[_Block] = []
    pending_list: list[str] = []

    def flush_list() -> None:
        nonlocal pending_list
        if pending_list:
            blocks.append(_Block("list", "\n".join(f"• {item}" for item in pending_list)))
            pending_list = []

    for el in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
        # Skip nested content that a parent block already captured.
        if el.name != "blockquote" and el.find_parent("blockquote") is not None:
            continue
        if el.name == "li" and el.find_parent("li") is not None:
            continue
        if el.name == "p" and el.find_parent("li") is not None:
            continue

        text = _clean(el.get_text(" ", strip=True))
        if not text:
            continue

        if el.name == "li":
            pending_list.append(text)
            continue
        flush_list()

        if el.name.startswith("h"):
            blocks.append(_Block("heading", text, level=int(el.name[1])))
        elif el.name == "blockquote":
            blocks.append(_Block("quote", text))
        else:
            blocks.append(_Block("paragraph", text))
    flush_list()
    return blocks


def _group_sections(blocks: list[_Block]) -> tuple[str | None, list[_Section]]:
    title: str | None = None
    sections: list[_Section] = [_Section(heading=None)]
    for b in blocks:
        if b.kind == "heading":
            if b.level == 1 and title is None and not sections[0].blocks and len(sections) == 1:
                title = b.text
                continue
            sections.append(_Section(heading=b.text))
        else:
            sections[-1].blocks.append(b)
    return title, [s for s in sections if s.blocks]


def _split_long_paragraph(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        if current and len(current) + 1 + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def _pack_paragraphs(paragraphs: list[str], min_chars: int, max_chars: int) -> list[str]:
    """Greedy packing of consecutive paragraphs into [min_chars, max_chars] chunks."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        for piece in _split_long_paragraph(para, max_chars):
            extra = len(piece) + (2 if current else 0)
            if current and current_len + extra > max_chars:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
                extra = len(piece)
            current.append(piece)
            current_len += extra
    if current:
        chunks.append("\n\n".join(current))
    # Merge a tiny trailing chunk into its predecessor.
    if len(chunks) >= 2 and len(chunks[-1]) < min_chars and len(chunks[-2]) + len(chunks[-1]) <= max_chars * 1.3:
        chunks[-2] = chunks[-2] + "\n\n" + chunks[-1]
        chunks.pop()
    return chunks


def hook_score(sentence: str) -> float:
    """How well a single sentence would work as a standalone post opener."""
    s = sentence.strip()
    n = len(s)
    if n < 40 or n > 220:
        return 0.0
    words = re.findall(r"[a-zA-Z']+", s.lower())
    if not words:
        return 0.0
    score = 1.0
    if words[0] in _WEAK_STARTS:
        score -= 0.6  # depends on the previous sentence
    if re.search(r"\d", s):
        score += 0.8
    if s.endswith("?"):
        score += 0.5
    if any(w in ("you", "your", "you're") for w in words):
        score += 0.4
    if any(w == "i" or w in ("i'm", "i've", "my") for w in words):
        score += 0.3  # first-person confession/story hooks
    if words[0] in _HOOK_IMPERATIVES:
        score += 0.5
    if any(c in s.lower() for c in _CONTRAST_WORDS):
        score += 0.3
    if 60 <= n <= 140:
        score += 0.3
    return max(score, 0.0)


def chunk_post_score(text: str, kind: str, heading: str | None) -> float:
    n = len(text)
    score = 1.0
    if kind == "quote":
        score += 0.6
    if kind == "hook":
        score += 0.4
    if kind == "list":
        score += 0.2
    if heading:
        score += 0.2
    if re.search(r"\d", text):
        score += 0.3
    if "?" in text:
        score += 0.2
    if re.search(r"\byou(r)?\b", text, re.I):
        score += 0.2
    if 200 <= n <= 600:
        score += 0.3
    elif n > 900:
        score -= 0.3
    return round(score, 3)


def chunk_article(
    content: str,
    source_format: str,
    *,
    min_chars: int = 150,
    max_chars: int = 700,
    hook_chunks: int = 2,
) -> tuple[str | None, list[Chunk]]:
    """Return (detected_title, chunks) for the article body.

    Raises :class:`ChunkingError` when nothing usable is found.
    """
    if source_format not in ("html", "markdown"):
        raise ChunkingError(f"Unsupported source_format {source_format!r}")
    root = _to_root(content, source_format)
    blocks = _extract_blocks(root)
    title, sections = _group_sections(blocks)
    if not sections:
        raise ChunkingError("No paragraphs, lists or quotes found in the article")

    chunks: list[Chunk] = []
    paragraph_pool: list[tuple[str | None, str]] = []  # (heading, paragraph) for hooks

    for section in sections:
        paragraphs: list[str] = []

        def flush_paragraphs() -> None:
            nonlocal paragraphs
            for text in _pack_paragraphs(paragraphs, min_chars, max_chars):
                if len(text) >= min(min_chars, 80):
                    chunks.append(Chunk(index=len(chunks), kind="section", heading=section.heading, text=text))
            paragraphs = []

        for b in section.blocks:
            if b.kind == "paragraph":
                paragraphs.append(b.text)
                paragraph_pool.append((section.heading, b.text))
            elif b.kind == "list":
                flush_paragraphs()
                if len(b.text) >= 40:
                    chunks.append(Chunk(index=len(chunks), kind="list", heading=section.heading, text=b.text))
            elif b.kind == "quote":
                flush_paragraphs()
                if len(b.text) >= 40:
                    chunks.append(Chunk(index=len(chunks), kind="quote", heading=section.heading, text=b.text))
        flush_paragraphs()

    # Hooks: best standalone sentences, deduplicated against quotes.
    if hook_chunks > 0:
        existing = {c.text.strip().lower() for c in chunks if c.kind == "quote"}
        candidates: list[tuple[float, str, str | None, str]] = []
        for heading, para in paragraph_pool:
            for sentence in split_sentences(para):
                s = hook_score(sentence)
                if s >= 1.5 and sentence.strip().lower() not in existing:
                    candidates.append((s, sentence, heading, para))
        candidates.sort(key=lambda c: c[0], reverse=True)
        seen: set[str] = set()
        for s, sentence, heading, para in candidates:
            key = sentence.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            chunks.append(Chunk(index=len(chunks), kind="hook", heading=heading, text=sentence, context=para))
            if len([c for c in chunks if c.kind == "hook"]) >= hook_chunks:
                break

    if not chunks:
        raise ChunkingError("Article parsed but produced no chunks above the minimum size")

    for c in chunks:
        c.post_score = chunk_post_score(c.text, c.kind, c.heading)
    return title, chunks


def select_chunks(chunks: list[Chunk], max_posts: int) -> list[Chunk]:
    """Keep the top ``max_posts`` by score, returned in document order."""
    if len(chunks) <= max_posts:
        return list(chunks)
    top = sorted(chunks, key=lambda c: c.post_score, reverse=True)[:max_posts]
    keep = {c.index for c in top}
    return [c for c in chunks if c.index in keep]
