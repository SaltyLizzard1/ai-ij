"""Command-line entry point: ``python -m social_pipeline <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from .config import Settings
from .errors import PipelineError
from .library.tagger import AnthropicVisionTagger, MockVisionTagger, VisionTagger
from .llm import build_provider
from .pipeline import RunOptions, SocialPipeline
from .storage import Storage


def build_tagger(settings: Settings) -> VisionTagger | None:
    if settings.llm_provider == "anthropic":
        return AnthropicVisionTagger(
            model=settings.resolved_model, api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds, server_fallbacks=settings.anthropic_server_fallbacks,
        )
    if settings.llm_provider == "mock":
        return MockVisionTagger()
    logging.getLogger(__name__).warning(
        "Vision tagging is implemented for the Anthropic provider only; photos will not be auto-tagged with %s",
        settings.llm_provider,
    )
    return None


def _parse_month(value: str | None) -> int | None:
    if not value:
        return None
    if "-" in value:  # 2026-09
        return int(value.split("-")[1])
    return int(value)


def _pipeline(settings: Settings, *, dry_run: bool = False) -> tuple[SocialPipeline, Storage]:
    if dry_run:
        settings.llm_provider = "mock"
    provider = build_provider(settings)
    tagger = build_tagger(settings)
    storage = Storage(settings.db_path)
    return SocialPipeline(settings, storage, provider, tagger=tagger), storage


def cmd_init_db(args: argparse.Namespace, settings: Settings) -> int:
    with Storage(settings.db_path) as st:
        print(f"Database ready at {st.db_path}")
        print(json.dumps(st.image_stats(), indent=2))
    return 0


def cmd_scan(args: argparse.Namespace, settings: Settings) -> int:
    months = set(args.months.split(",")) if args.months else None
    pipe, storage = _pipeline(settings, dry_run=True)
    with storage:
        stats = pipe.scan_library(months=months)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_tag(args: argparse.Namespace, settings: Settings) -> int:
    month = _parse_month(args.month) or datetime.now().month
    pipe, storage = _pipeline(settings, dry_run=args.dry_run)
    with storage:
        if args.list:
            for img in pipe.tag_images(target_month=month, limit=args.limit, dry_run=True):
                print(f"{img.path}\tblur={img.blur}\tmonth={img.year}-{img.month:02d}")
            return 0
        tagged = pipe.tag_images(target_month=month, limit=args.limit)
        for img in tagged:
            t = img.tags
            print(f"{img.path}: {t.subject} | themes={','.join(t.themes)} | moods={','.join(t.moods)}")  # type: ignore[union-attr]
        print(f"Tagged {len(tagged)} photo(s). Library: {json.dumps(storage.image_stats()['by_month'])}")
    return 0


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    text = None
    if args.stdin:
        text = sys.stdin.read()
    options = RunOptions(
        url=args.url, path=args.file, text=text, title=args.title, source_format=args.format,
        target_month=_parse_month(args.month), max_posts=args.max_posts,
        platforms=args.platforms.split(",") if args.platforms else None,
        auto_tag=not args.no_auto_tag, tag_limit=args.tag_limit, output_path=args.out,
    )
    pipe, storage = _pipeline(settings, dry_run=args.dry_run)
    with storage:
        result = pipe.run(options)
    print(f"[{result.status}] {len(result.packages)} post(s) from '{result.article.title}' "
          f"({result.chunks_selected}/{result.chunks_total} chunks); tagged {result.images_tagged} photo(s)")
    for pkg in result.packages:
        print(f"  {pkg.suggested_post_date}  chunk {pkg.chunk.index:<2} {pkg.chunk.kind:<8} -> {pkg.match.image.path}  "
              f"(score {pkg.match.score:.1f}{', fallback' if pkg.match.is_fallback else ''})")
    for w in result.warnings:
        print(f"  warning: {w}")
    for e in result.errors:
        print(f"  ERROR: {e}")
    if result.output_path:
        print(f"Output: {result.output_path}")
    return 0 if result.status == "succeeded" else (2 if result.status == "partial" else 1)


def cmd_posts(args: argparse.Namespace, settings: Settings) -> int:
    with Storage(settings.db_path) as st:
        posts = st.list_posts(article_id=args.article, status=args.status)
        if args.json:
            print(json.dumps(posts, indent=2, ensure_ascii=False))
            return 0
        for p in posts:
            print(f"{p['suggested_post_date']}  {p['status']:<9} {p['id']}  chunk {p['chunk_index']} ({p['kind']})  {p['image_path']}")
            for v in p["variants"]:
                first = v["body"].splitlines()[0] if v["body"] else ""
                print(f"    {v['platform']:<9} {v['char_count']:>5} chars  {first[:80]}")
    return 0


def cmd_set_status(args: argparse.Namespace, settings: Settings) -> int:
    with Storage(settings.db_path) as st:
        st.set_post_status(args.post_id, args.status)
    print(f"{args.post_id} -> {args.status}")
    return 0


def cmd_status(args: argparse.Namespace, settings: Settings) -> int:
    with Storage(settings.db_path) as st:
        print(json.dumps({"db": str(st.db_path), "image_root": settings.image_root, "provider": settings.llm_provider,
                          "model": settings.resolved_model, "images": st.image_stats()}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="social-pipeline", description="Article -> matched photos -> platform posts.")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("--env", default=".env", help="path to a .env file (default: ./.env)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the SQLite database").set_defaults(func=cmd_init_db)
    sub.add_parser("status", help="show configuration and library counts").set_defaults(func=cmd_status)

    s = sub.add_parser("scan", help="index photos under IMAGE_ROOT (YYYY-MM folders) with blur scores")
    s.add_argument("--months", help="comma-separated folder names to limit the scan, e.g. 2026-09,2026-08")
    s.set_defaults(func=cmd_scan)

    t = sub.add_parser("tag", help="describe untagged photos with the vision model")
    t.add_argument("--month", help="target month (9 or 2026-09); default: current month")
    t.add_argument("--limit", type=int, help="max photos to tag (default TAG_MAX_PER_RUN)")
    t.add_argument("--list", action="store_true", help="only list the candidates, do not call the API")
    t.add_argument("--dry-run", action="store_true", help="use the mock tagger (no API calls)")
    t.set_defaults(func=cmd_tag)

    r = sub.add_parser("run", help="generate posts for one article")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="article URL")
    src.add_argument("--file", help="local .md/.html file")
    src.add_argument("--stdin", action="store_true", help="read the article from stdin")
    r.add_argument("--title")
    r.add_argument("--format", choices=["html", "markdown"], help="override format detection")
    r.add_argument("--month", help="target month for photos (default: current month)")
    r.add_argument("--max-posts", type=int)
    r.add_argument("--platforms", help="comma-separated, e.g. linkedin,x,instagram,facebook")
    r.add_argument("--no-auto-tag", action="store_true", help="do not tag new photos during this run")
    r.add_argument("--tag-limit", type=int, help="max photos to tag during this run")
    r.add_argument("--out", help="output JSON path (default OUTPUT_DIR/<article>-<stamp>.json)")
    r.add_argument("--dry-run", action="store_true", help="mock LLM + tagger: exercise the pipeline without API calls")
    r.set_defaults(func=cmd_run)

    l = sub.add_parser("posts", help="list generated posts")
    l.add_argument("--article", help="article id")
    l.add_argument("--status", choices=["draft", "approved", "scheduled", "published", "rejected"])
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_posts)

    ss = sub.add_parser("set-status", help="update a post's workflow status")
    ss.add_argument("post_id")
    ss.add_argument("status", choices=["draft", "approved", "scheduled", "published", "rejected"])
    ss.set_defaults(func=cmd_set_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        settings = Settings.from_env(args.env)
        return int(args.func(args, settings))
    except (PipelineError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
