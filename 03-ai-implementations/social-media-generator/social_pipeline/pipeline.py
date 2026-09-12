"""End-to-end orchestration: article -> chunks -> images -> captions -> JSON."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .articles import load_article
from .captions import CaptionGenerator, CaptionRules
from .chunker import chunk_article, select_chunks
from .config import Settings
from .errors import PipelineError
from .keywords import analyse_chunk_text
from .library.matcher import ImageMatcher
from .library.scanner import LibraryScanner
from .library.tagger import VisionTagger, prepare_image, select_tag_candidates
from .llm.base import CaptionProvider
from .models import Article, Chunk, ImageAsset, PostPackage, stable_id
from .scheduler import ScheduleConfig, platform_post_at, suggest_post_date
from .storage import Storage
from .utils import with_retries

log = logging.getLogger(__name__)


@dataclass
class RunOptions:
    url: str | None = None
    path: str | None = None
    text: str | None = None
    title: str | None = None
    source_format: str | None = None
    target_month: int | None = None  # defaults to the current month
    max_posts: int | None = None
    platforms: list[str] | None = None
    auto_tag: bool = True
    tag_limit: int | None = None
    output_path: str | None = None
    write_output: bool = True


@dataclass
class PipelineResult:
    run_id: str
    article: Article
    packages: list[PostPackage]
    chunks_total: int
    chunks_selected: int
    images_tagged: int
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    output_path: str | None = None
    started_at: str = ""
    finished_at: str = ""

    @property
    def status(self) -> str:
        if self.packages and not self.errors:
            return "succeeded"
        if self.packages:
            return "partial"
        return "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "article": {
                "id": self.article.id,
                "title": self.article.title,
                "source_url": self.article.source_url,
                "source_format": self.article.source_format,
            },
            "stats": {
                "chunks_total": self.chunks_total,
                "chunks_selected": self.chunks_selected,
                "posts_generated": len(self.packages),
                "images_tagged_this_run": self.images_tagged,
                "llm_usage": self.usage,
            },
            "posts": [p.to_dict() for p in self.packages],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


class SocialPipeline:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        provider: CaptionProvider,
        *,
        tagger: VisionTagger | None = None,
        scanner: LibraryScanner | None = None,
        sleep=None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.provider = provider
        self.tagger = tagger
        self.scanner = scanner or LibraryScanner(
            settings.image_root, records_dir=settings.records_dir, skip_folders=settings.skip_folders
        )
        self.matcher = ImageMatcher(strict_month=settings.strict_month)
        self.schedule = ScheduleConfig(
            timezone=settings.timezone, weekdays_only=settings.weekdays_only, seasonal=settings.seasonal_scheduling
        )
        self._sleep = sleep

    # ----------------------------------------------------------- library
    def scan_library(self, *, months: set[str] | None = None) -> dict[str, Any]:
        assets = self.scanner.scan(months=months)
        inserted, updated = self.storage.upsert_images(assets)
        stats = self.storage.image_stats()
        stats.update({"inserted": inserted, "updated": updated})
        return stats

    def tag_images(self, *, target_month: int, limit: int | None = None, dry_run: bool = False) -> list[ImageAsset]:
        """Tag the best untagged candidates. Returns the images that were tagged."""
        s = self.settings
        images = self.storage.list_images()
        candidates = select_tag_candidates(
            images,
            target_month=target_month,
            max_blur=s.max_blur,
            min_contrast=s.min_contrast,
            require_quality_record=s.require_quality_record,
            limit=limit if limit is not None else s.tag_max_per_run,
        )
        if dry_run or not candidates:
            return candidates
        if self.tagger is None:
            log.warning("No vision tagger configured (provider=%s); skipping tagging", s.llm_provider)
            return []
        tagged: list[ImageAsset] = []
        for img in candidates:
            abs_path = self.scanner.absolute_path(img)
            try:
                data, media_type = prepare_image(abs_path, max_edge=s.tag_image_max_edge)
                hint = f"Taken {img.year or ''}-{img.month:02d}"
                kwargs = {"attempts": s.llm_max_retries, "label": f"tag {img.file_name}"}
                if self._sleep is not None:
                    kwargs["sleep"] = self._sleep
                tags = with_retries(lambda: self.tagger.tag(data, media_type, hint=hint), **kwargs)  # type: ignore[union-attr]
                self.storage.save_tags(img.id, tags)
                img.tags = tags
                tagged.append(img)
                log.info("Tagged %s: %s [%s]", img.path, tags.subject, ", ".join(tags.themes))
            except PipelineError as exc:
                log.error("Tagging failed for %s: %s", img.path, exc)
        return tagged

    # --------------------------------------------------------------- run
    def _analyse(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            a = analyse_chunk_text(c.text, c.heading, c.context)
            c.keywords, c.themes, c.moods = a["keywords"], a["themes"], a["moods"]

    def run(self, options: RunOptions) -> PipelineResult:
        s = self.settings
        started = datetime.now(timezone.utc)
        run_id = stable_id("run", started.isoformat(), options.url or options.path or (options.text or "")[:100])
        platforms = list(options.platforms or s.platforms)
        max_posts = options.max_posts or s.max_posts_per_article
        target_month = options.target_month or datetime.now().month

        # 1. Article
        article = load_article(
            url=options.url, path=options.path, text=options.text, title=options.title, source_format=options.source_format
        )
        self.storage.upsert_article(article)
        self.storage.start_run(run_id, article.id, self.provider.name, self.provider.model_name)

        result = PipelineResult(
            run_id=run_id, article=article, packages=[], chunks_total=0, chunks_selected=0, images_tagged=0,
            started_at=started.isoformat(),
        )
        try:
            # 2. Chunk + analyse
            detected_title, chunks = chunk_article(
                article.raw_content, article.source_format,
                min_chars=s.chunk_min_chars, max_chars=s.chunk_max_chars, hook_chunks=s.hook_chunks,
            )
            if not options.title and detected_title and article.title == "Untitled":
                article.title = detected_title
                self.storage.upsert_article(article)
            self._analyse(chunks)
            self.storage.replace_chunks(article.id, chunks)
            selected = select_chunks(chunks, max_posts)
            result.chunks_total, result.chunks_selected = len(chunks), len(selected)

            # 3. Images: make sure the library is indexed, then tag on demand
            images = self.storage.list_images()
            if not images and Path(s.image_root).is_dir():
                log.info("Image table empty; scanning %s", s.image_root)
                self.scan_library()
                images = self.storage.list_images()
            if options.auto_tag and self.tagger is not None:
                tagged = self.tag_images(target_month=target_month, limit=options.tag_limit)
                result.images_tagged = len(tagged)
                if tagged:
                    images = self.storage.list_images()
            if not images:
                raise PipelineError(f"No photos indexed under {s.image_root}; run `scan` first")

            # 4. Match -> caption -> schedule, one chunk at a time, failures isolated
            rules = CaptionRules(
                brand_voice=s.brand_voice_text(), brand_name=s.brand_name, forbid_em_dashes=s.forbid_em_dashes,
                forbid_financial_figures=s.forbid_financial_figures, allow_hashtags=s.allow_hashtags,
                banned_phrases=s.banned_phrases,
            )
            generator = CaptionGenerator(self.provider, rules, platforms, max_retries=s.llm_max_retries, sleep=self._sleep)
            used_in_run: set[str] = set()
            for position, chunk in enumerate(selected):
                try:
                    match = self.matcher.best(chunk, images, target_month=target_month, exclude_ids=used_in_run)
                    captions = generator.generate(article.title, chunk, match)
                    post_date = suggest_post_date(match.image.month, position, len(selected), self.schedule)
                    for p, post in captions.posts.items():
                        post.suggested_post_at = platform_post_at(post_date, p, self.schedule)
                    package = PostPackage(
                        id=stable_id(article.id, chunk.id or str(chunk.index), match.image.id),
                        article_id=article.id, chunk=chunk, match=match, suggested_post_date=post_date,
                        platforms=captions.posts, image_alt_text=captions.image_alt_text or (match.image.tags.alt_text if match.image.tags else ""),
                        theme=captions.theme, provider=captions.provider, model=captions.model,
                    )
                    self.storage.save_package(package, run_id=run_id, warnings=captions.warnings)
                    self.storage.mark_image_used(match.image.id)
                    match.image.used_count += 1
                    used_in_run.add(match.image.id)
                    result.packages.append(package)
                    result.warnings.extend(f"chunk {chunk.index}: {w}" for w in captions.warnings)
                    for k, v in captions.usage.items():
                        result.usage[k] = result.usage.get(k, 0) + int(v)
                    log.info("Post %d/%d ready: chunk %d (%s) + %s on %s", position + 1, len(selected), chunk.index, chunk.kind, match.image.path, post_date)
                except PipelineError as exc:
                    log.error("Chunk %d failed: %s", chunk.index, exc)
                    result.errors.append({"chunk_index": chunk.index, "kind": chunk.kind, "error": str(exc), "retryable": exc.retryable})
        except PipelineError as exc:
            result.errors.append({"stage": "pipeline", "error": str(exc), "retryable": exc.retryable})
            log.error("Run failed: %s", exc)

        result.finished_at = datetime.now(timezone.utc).isoformat()
        if options.write_output:
            result.output_path = self._write_output(result, options.output_path)
        self.storage.finish_run(
            run_id, result.status,
            {"posts": len(result.packages), "chunks": result.chunks_total, "errors": len(result.errors), "usage": result.usage},
            error="; ".join(e["error"] for e in result.errors) or None,
        )
        return result

    def _write_output(self, result: PipelineResult, output_path: str | None) -> str:
        if output_path:
            out = Path(output_path)
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out = Path(self.settings.output_dir) / f"{result.article.id}-{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("Wrote %s", out)
        return str(out)
