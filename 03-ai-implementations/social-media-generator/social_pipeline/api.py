"""HTTP API + review UI. Run with ``social-pipeline serve``.

Binds to 127.0.0.1 by default and has no authentication: it is meant to run on
the machine that has the camera roll and the database.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .errors import PipelineError, StorageError
from .jobs import Job, JobRunner
from .library.quality import append_scores, record_path_for, score_image, unscored_photos
from .library.tagger import AnthropicVisionTagger, MockVisionTagger, VisionTagger
from .llm import build_provider
from .pipeline import RunOptions, SocialPipeline
from .platforms import PLATFORMS
from .storage import Storage

log = logging.getLogger(__name__)
UI_DIR = Path(__file__).with_name("ui")
STATUSES = ("draft", "approved", "scheduled", "published", "rejected")


# ----------------------------------------------------------------- schemas
class PostUpdate(BaseModel):
    status: str | None = None
    suggested_post_date: date | None = None
    notes: str | None = None
    image_alt_text: str | None = None


class VariantUpdate(BaseModel):
    body: str
    hashtags: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    path: str | None = None
    title: str | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    max_posts: int | None = Field(default=None, ge=1, le=20)
    platforms: list[str] | None = None
    auto_tag: bool = True
    tag_limit: int | None = None
    dry_run: bool = False


class TagRequest(BaseModel):
    month: int | None = Field(default=None, ge=1, le=12)
    limit: int | None = Field(default=None, ge=1, le=500)


class LibraryRequest(BaseModel):
    months: list[str] | None = None


# ----------------------------------------------------------------- factory
def build_tagger(settings: Settings, *, dry_run: bool = False) -> VisionTagger | None:
    if dry_run or settings.llm_provider == "mock":
        return MockVisionTagger()
    if settings.llm_provider == "anthropic":
        return AnthropicVisionTagger(
            model=settings.resolved_model, api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds, server_fallbacks=settings.anthropic_server_fallbacks,
        )
    return None


def create_app(settings: Settings, *, jobs: JobRunner | None = None) -> FastAPI:
    app = FastAPI(title="Social Pipeline", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    runner = jobs or JobRunner()
    thumb_dir = Path(settings.output_dir) / "thumbs"

    def storage() -> Storage:
        st = Storage(settings.db_path)
        try:
            yield st
        finally:
            st.close()

    def make_pipeline(st: Storage, *, dry_run: bool = False) -> SocialPipeline:
        s = settings
        if dry_run:
            from dataclasses import replace

            s = replace(settings, llm_provider="mock")
        return SocialPipeline(s, st, build_provider(s), tagger=build_tagger(settings, dry_run=dry_run))

    def submit(kind: str, fn) -> JSONResponse:  # type: ignore[no-untyped-def]
        try:
            job = runner.submit(kind, fn)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(job.to_dict(), status_code=202)

    # ------------------------------------------------------------- errors
    @app.exception_handler(PipelineError)
    async def _pipeline_error(_, exc: PipelineError) -> JSONResponse:
        code = 404 if isinstance(exc, StorageError) and "No post" in str(exc) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    # ----------------------------------------------------------------- UI
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return (UI_DIR / "index.html").read_text(encoding="utf-8")

    # -------------------------------------------------------------- meta
    @app.get("/api/status")
    def status(st: Storage = Depends(storage)) -> dict[str, Any]:
        return {
            "db": str(st.db_path), "image_root": settings.image_root, "records_dir": settings.records_dir,
            "provider": settings.llm_provider, "model": settings.resolved_model, "platforms": list(settings.platforms),
            "timezone": settings.timezone, "images": st.image_stats(), "posts": st.post_counts(),
            "current_job": runner.current().to_dict() if runner.current() else None,
        }

    @app.get("/api/platforms")
    def platforms() -> dict[str, Any]:
        return {
            k: {"display_name": v.display_name, "max_chars": v.max_chars, "max_words": v.max_words,
                "hashtags": list(v.hashtags), "hook_chars": v.hook_chars, "post_hour": v.post_hour}
            for k, v in PLATFORMS.items()
        }

    @app.get("/api/articles")
    def articles(st: Storage = Depends(storage)) -> list[dict[str, Any]]:
        return st.list_articles()

    # ------------------------------------------------------------- posts
    @app.get("/api/posts")
    def list_posts(
        status: str | None = Query(default=None), article: str | None = Query(default=None), st: Storage = Depends(storage)
    ) -> list[dict[str, Any]]:
        if status and status not in STATUSES:
            raise HTTPException(400, f"status must be one of {STATUSES}")
        return st.list_posts(article_id=article, status=status)

    @app.get("/api/posts/{post_id}")
    def get_post(post_id: str, st: Storage = Depends(storage)) -> dict[str, Any]:
        post = st.get_post(post_id)
        if not post:
            raise HTTPException(404, "post not found")
        return post

    @app.patch("/api/posts/{post_id}")
    def update_post(post_id: str, body: PostUpdate, st: Storage = Depends(storage)) -> dict[str, Any]:
        if body.status and body.status not in STATUSES:
            raise HTTPException(400, f"status must be one of {STATUSES}")
        return st.update_post(
            post_id, status=body.status,
            suggested_post_date=body.suggested_post_date.isoformat() if body.suggested_post_date else None,
            notes=body.notes, image_alt_text=body.image_alt_text,
        )

    @app.put("/api/posts/{post_id}/variants/{platform}")
    def update_variant(post_id: str, platform: str, body: VariantUpdate, st: Storage = Depends(storage)) -> dict[str, Any]:
        if platform not in PLATFORMS:
            raise HTTPException(400, f"unknown platform {platform}")
        if not body.body.strip():
            raise HTTPException(400, "body must not be empty")
        spec = PLATFORMS[platform]
        full_len = len(body.body.strip()) + (2 + len(" ".join(body.hashtags)) if body.hashtags else 0)
        if full_len > spec.max_chars:
            raise HTTPException(400, f"{spec.display_name} allows {spec.max_chars} characters; got {full_len}")
        return st.update_variant(post_id, platform, body=body.body, hashtags=body.hashtags)

    @app.get("/api/export")
    def export(status: str = Query(default="approved"), article: str | None = None, st: Storage = Depends(storage)) -> dict[str, Any]:
        """Approved posts in a publishing-friendly shape (absolute image paths)."""
        posts = st.list_posts(article_id=article, status=status)
        root = Path(settings.image_root)
        out = []
        for p in posts:
            out.append({
                "post_id": p["id"], "status": p["status"], "article": p["article"], "theme": p["theme"],
                "suggested_post_date": p["suggested_post_date"],
                "image": {"path": str(root / Path(p["image"]["path"])), "relative_path": p["image"]["path"],
                          "alt_text": p["image_alt_text"] or p["image"]["alt_text"]},
                "platforms": {
                    v["platform"]: {
                        "text": v["body"] + ("\n\n" + " ".join(v["hashtags"]) if v["hashtags"] else ""),
                        "body": v["body"], "hashtags": v["hashtags"], "suggested_post_at": v["suggested_post_at"],
                    } for v in p["variants"]
                },
            })
        return {"exported_at": datetime.now().astimezone().isoformat(), "count": len(out), "posts": out}

    # ------------------------------------------------------------ images
    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, st: Storage = Depends(storage)) -> FileResponse:
        img = st.get_image(image_id)
        if not img:
            raise HTTPException(404, "image not found")
        path = Path(settings.image_root) / Path(img.path)
        if not path.is_file():
            raise HTTPException(404, f"file missing on disk: {path}")
        return FileResponse(path)

    @app.get("/api/images/{image_id}/thumb")
    def image_thumb(image_id: str, w: int = Query(default=640, ge=64, le=2048), st: Storage = Depends(storage)) -> Response:
        img = st.get_image(image_id)
        if not img:
            raise HTTPException(404, "image not found")
        src = Path(settings.image_root) / Path(img.path)
        if not src.is_file():
            raise HTTPException(404, f"file missing on disk: {src}")
        thumb_dir.mkdir(parents=True, exist_ok=True)
        cached = thumb_dir / f"{image_id}-{w}.jpg"
        if cached.is_file() and cached.stat().st_mtime >= src.stat().st_mtime:
            return FileResponse(cached, media_type="image/jpeg")
        try:
            from PIL import Image, ImageOps

            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((w, w))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82, optimize=True)
        except OSError as exc:
            raise HTTPException(415, f"cannot render {src.name}: {exc}") from exc
        cached.write_bytes(buf.getvalue())
        return Response(buf.getvalue(), media_type="image/jpeg")

    # -------------------------------------------------------------- jobs
    @app.get("/api/jobs")
    def jobs_list() -> list[dict[str, Any]]:
        return [j.to_dict() for j in runner.recent()]

    @app.get("/api/jobs/{job_id}")
    def job_get(job_id: str) -> dict[str, Any]:
        job = runner.get(job_id)
        if not job:
            raise HTTPException(404, "job not found")
        return job.to_dict()

    @app.post("/api/library/scan", status_code=202)
    def library_scan(body: LibraryRequest | None = None) -> JSONResponse:
        months = set(body.months) if body and body.months else None

        def work(job: Job) -> dict[str, Any]:
            with Storage(settings.db_path) as st:
                return make_pipeline(st, dry_run=True).scan_library(months=months)

        return submit("scan", work)

    @app.post("/api/library/score", status_code=202)
    def library_score(body: LibraryRequest | None = None) -> JSONResponse:
        months = set(body.months) if body and body.months else None
        if not settings.records_dir:
            raise HTTPException(400, "RECORDS_DIR is not configured")

        def work(job: Job) -> dict[str, Any]:
            root = Path(settings.image_root)
            csv_path = Path(settings.records_dir) / "blur2.csv"  # type: ignore[arg-type]
            todo = unscored_photos(root, csv_path, months=months, skip_folders=settings.skip_folders)
            scores, failed = [], []
            for f, rel in todo:
                try:
                    scores.append(score_image(f, record_path=record_path_for(root, rel)))
                    job.log.append(f"scored {rel}: blur={scores[-1].blur:.3f}")
                except PipelineError as exc:
                    failed.append({"path": rel, "error": str(exc)})
            appended = append_scores(csv_path, scores)
            with Storage(settings.db_path) as st:
                stats = make_pipeline(st, dry_run=True).scan_library(months=months)
            return {"scored": appended, "failed": failed, "library": stats}

        return submit("score", work)

    @app.post("/api/library/tag", status_code=202)
    def library_tag(body: TagRequest | None = None) -> JSONResponse:
        month = (body.month if body and body.month else None) or datetime.now().month
        limit = body.limit if body else None

        def work(job: Job) -> dict[str, Any]:
            with Storage(settings.db_path) as st:
                pipe = make_pipeline(st)
                tagged = pipe.tag_images(target_month=month, limit=limit)
                return {"tagged": [{"path": i.path, "subject": i.tags.subject if i.tags else None} for i in tagged],
                        "library": st.image_stats()}

        return submit("tag", work)

    @app.post("/api/runs", status_code=202)
    def run_article(body: RunRequest) -> JSONResponse:
        if sum(1 for x in (body.url, body.text, body.path) if x) != 1:
            raise HTTPException(400, "provide exactly one of url, text or path")
        if body.platforms:
            bad = [p for p in body.platforms if p not in PLATFORMS]
            if bad:
                raise HTTPException(400, f"unknown platforms: {bad}")

        def work(job: Job) -> dict[str, Any]:
            with Storage(settings.db_path) as st:
                pipe = make_pipeline(st, dry_run=body.dry_run)
                result = pipe.run(RunOptions(
                    url=body.url, text=body.text, path=body.path, title=body.title, target_month=body.month,
                    max_posts=body.max_posts, platforms=body.platforms, auto_tag=body.auto_tag, tag_limit=body.tag_limit,
                ))
                return {
                    "run_id": result.run_id, "status": result.status, "article_id": result.article.id,
                    "article_title": result.article.title, "posts": len(result.packages),
                    "post_ids": [p.id for p in result.packages], "chunks_total": result.chunks_total,
                    "images_tagged": result.images_tagged, "errors": result.errors, "warnings": result.warnings,
                    "usage": result.usage, "output_path": result.output_path,
                }

        return submit("run", work)

    return app


def serve(settings: Settings, *, host: str = "127.0.0.1", port: int = 8765, reload: bool = False) -> None:
    import uvicorn

    app = create_app(settings)
    log.info("Review UI: http://%s:%d/   API docs: http://%s:%d/api/docs", host, port, host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
