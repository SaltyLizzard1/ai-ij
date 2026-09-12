"""SQLite repository. Standard library only; schema lives in ``schema.sql``."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import StorageError
from .models import Article, Chunk, ImageAsset, ImageMatch, ImageTags, PlatformPost, PostPackage, stable_id

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        try:
            if str(self.db_path) != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False: FastAPI may open and close a per-request connection
            # on different worker threads. Each request/job still gets its own connection.
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            self._migrate()
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Could not open database {db_path}: {exc}") from exc

    def _migrate(self) -> None:
        """Add columns introduced after the first release to existing databases."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(generated_posts)")}
        with self.conn:
            if "reviewed_at" not in cols:
                self.conn.execute("ALTER TABLE generated_posts ADD COLUMN reviewed_at TEXT")
            if "notes" not in cols:
                self.conn.execute("ALTER TABLE generated_posts ADD COLUMN notes TEXT")
        vcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(post_variants)")}
        with self.conn:
            if "edited_at" not in vcols:
                self.conn.execute("ALTER TABLE post_variants ADD COLUMN edited_at TEXT")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ articles
    def upsert_article(self, article: Article) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO articles (id, title, source_url, source_format, raw_content, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title, source_url = excluded.source_url,
                        source_format = excluded.source_format, raw_content = excluded.raw_content,
                        content_hash = excluded.content_hash, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    """,
                    (article.id, article.title, article.source_url, article.source_format, article.raw_content, article.content_hash),
                )
        except sqlite3.Error as exc:
            raise StorageError(f"upsert_article failed: {exc}") from exc

    def replace_chunks(self, article_id: str, chunks: list[Chunk]) -> None:
        try:
            with self.conn:
                self.conn.execute("DELETE FROM article_chunks WHERE article_id = ?", (article_id,))
                for c in chunks:
                    c.article_id = article_id
                    c.id = c.id or stable_id(article_id, str(c.index), c.text[:200])
                    self.conn.execute(
                        """
                        INSERT INTO article_chunks
                            (id, article_id, chunk_index, kind, heading, body, context, keywords_json, themes_json, moods_json, post_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            c.id, article_id, c.index, c.kind, c.heading, c.text, c.context,
                            json.dumps(c.keywords), json.dumps(c.themes), json.dumps(c.moods), c.post_score,
                        ),
                    )
        except sqlite3.Error as exc:
            raise StorageError(f"replace_chunks failed: {exc}") from exc

    # -------------------------------------------------------------- images
    def upsert_images(self, assets: list[ImageAsset]) -> tuple[int, int]:
        """Insert new photos, refresh technical fields on known ones. Tags survive.

        Returns (inserted, updated). Photos no longer on disk are flagged missing.
        """
        now = _now()
        inserted = updated = 0
        try:
            with self.conn:
                seen_ids = []
                for a in assets:
                    seen_ids.append(a.id)
                    cur = self.conn.execute(
                        """
                        INSERT INTO images (id, path, file_name, month, year, width, height, blur, contrast, brightness,
                                            quality_source, first_seen_at, last_seen_at, missing)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        ON CONFLICT(id) DO UPDATE SET
                            path = excluded.path, file_name = excluded.file_name, month = excluded.month,
                            year = excluded.year,
                            width = COALESCE(excluded.width, images.width),
                            height = COALESCE(excluded.height, images.height),
                            blur = COALESCE(excluded.blur, images.blur),
                            contrast = COALESCE(excluded.contrast, images.contrast),
                            brightness = COALESCE(excluded.brightness, images.brightness),
                            quality_source = CASE WHEN excluded.quality_source = 'records' THEN 'records' ELSE images.quality_source END,
                            last_seen_at = excluded.last_seen_at, missing = 0
                        """,
                        (
                            a.id, a.path, a.file_name, a.month, a.year, a.width, a.height, a.blur, a.contrast,
                            a.brightness, a.quality_source, now, now,
                        ),
                    )
                    # rowcount is 1 for both insert and update; distinguish via first_seen_at
                    row = self.conn.execute("SELECT first_seen_at FROM images WHERE id = ?", (a.id,)).fetchone()
                    if row and row["first_seen_at"] == now:
                        inserted += 1
                    else:
                        updated += 1
                    del cur
                if seen_ids:
                    placeholders = ",".join("?" for _ in seen_ids)
                    self.conn.execute(
                        f"UPDATE images SET missing = 1 WHERE last_seen_at < ? AND id NOT IN ({placeholders})",
                        (now, *seen_ids),
                    )
        except sqlite3.Error as exc:
            raise StorageError(f"upsert_images failed: {exc}") from exc
        return inserted, updated

    def _row_to_image(self, row: sqlite3.Row) -> ImageAsset:
        tags = None
        if row["tagged_at"]:
            tags = ImageTags(
                subject=row["subject"] or "",
                description=row["description"] or "",
                keywords=_loads(row["keywords_json"], []),
                themes=_loads(row["themes_json"], []),
                moods=_loads(row["moods_json"], []),
                alt_text=row["alt_text"] or "",
                people_present=bool(row["people_present"]),
                text_present=bool(row["text_present"]),
                suitable_for_social=bool(row["suitable_for_social"]) if row["suitable_for_social"] is not None else True,
                tagged_at=row["tagged_at"],
                tag_model=row["tag_model"],
            )
        return ImageAsset(
            id=row["id"], path=row["path"], file_name=row["file_name"], month=row["month"], year=row["year"],
            width=row["width"], height=row["height"], blur=row["blur"], contrast=row["contrast"],
            brightness=row["brightness"], quality_source=row["quality_source"], tags=tags,
            used_count=row["used_count"], last_used_at=row["last_used_at"],
        )

    def list_images(self, *, months: list[int] | None = None, year: int | None = None, include_missing: bool = False) -> list[ImageAsset]:
        sql = "SELECT * FROM images WHERE 1=1"
        params: list[Any] = []
        if not include_missing:
            sql += " AND missing = 0"
        if months:
            sql += f" AND month IN ({','.join('?' for _ in months)})"
            params.extend(months)
        if year is not None:
            sql += " AND year = ?"
            params.append(year)
        sql += " ORDER BY year, month, path"
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"list_images failed: {exc}") from exc
        return [self._row_to_image(r) for r in rows]

    def get_image(self, image_id: str) -> ImageAsset | None:
        row = self.conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        return self._row_to_image(row) if row else None

    def save_tags(self, image_id: str, tags: ImageTags) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE images SET subject = ?, description = ?, alt_text = ?, keywords_json = ?, themes_json = ?,
                        moods_json = ?, people_present = ?, text_present = ?, suitable_for_social = ?, tagged_at = ?, tag_model = ?
                    WHERE id = ?
                    """,
                    (
                        tags.subject, tags.description, tags.alt_text, json.dumps(tags.keywords), json.dumps(tags.themes),
                        json.dumps(tags.moods), int(tags.people_present), int(tags.text_present),
                        int(tags.suitable_for_social), tags.tagged_at or _now(), tags.tag_model, image_id,
                    ),
                )
                self.conn.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
                rows = {(image_id, k.lower().strip(), "keyword") for k in tags.keywords if k.strip()}
                rows |= {(image_id, t, "theme") for t in tags.themes}
                rows |= {(image_id, m, "mood") for m in tags.moods}
                if tags.subject.strip():
                    rows.add((image_id, tags.subject.lower().strip(), "subject"))
                self.conn.executemany("INSERT OR IGNORE INTO image_tags (image_id, tag, tag_type) VALUES (?, ?, ?)", sorted(rows))
        except sqlite3.Error as exc:
            raise StorageError(f"save_tags failed: {exc}") from exc

    def mark_image_used(self, image_id: str) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE images SET used_count = used_count + 1, last_used_at = ? WHERE id = ?", (_now(), image_id)
                )
        except sqlite3.Error as exc:
            raise StorageError(f"mark_image_used failed: {exc}") from exc

    def image_stats(self) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN tagged_at IS NOT NULL THEN 1 ELSE 0 END) AS tagged,
                   SUM(CASE WHEN quality_source = 'records' THEN 1 ELSE 0 END) AS scored,
                   SUM(CASE WHEN missing = 1 THEN 1 ELSE 0 END) AS missing
            FROM images
            """
        ).fetchone()
        by_month = self.conn.execute(
            "SELECT year, month, COUNT(*) AS n, SUM(CASE WHEN tagged_at IS NOT NULL THEN 1 ELSE 0 END) AS tagged "
            "FROM images WHERE missing = 0 GROUP BY year, month ORDER BY year, month"
        ).fetchall()
        return {
            "total": row["total"] or 0, "tagged": row["tagged"] or 0, "scored": row["scored"] or 0, "missing": row["missing"] or 0,
            "by_month": [dict(r) for r in by_month],
        }

    # ---------------------------------------------------------------- runs
    def start_run(self, run_id: str, article_id: str | None, provider: str, model: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO pipeline_runs (id, article_id, started_at, status, provider, model) VALUES (?, ?, ?, 'running', ?, ?)",
                (run_id, article_id, _now(), provider, model),
            )

    def finish_run(self, run_id: str, status: str, stats: dict[str, Any], error: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE pipeline_runs SET finished_at = ?, status = ?, stats_json = ?, error = ? WHERE id = ?",
                (_now(), status, json.dumps(stats), error, run_id),
            )

    # --------------------------------------------------------------- posts
    def save_package(self, package: PostPackage, *, run_id: str | None, warnings: list[str]) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO generated_posts (id, run_id, article_id, chunk_id, image_id, match_score, match_reasons_json,
                        is_fallback_image, theme, image_alt_text, suggested_post_date, provider, model, warnings_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET run_id = excluded.run_id, match_score = excluded.match_score,
                        match_reasons_json = excluded.match_reasons_json, is_fallback_image = excluded.is_fallback_image,
                        theme = excluded.theme, image_alt_text = excluded.image_alt_text,
                        suggested_post_date = excluded.suggested_post_date, provider = excluded.provider,
                        model = excluded.model, warnings_json = excluded.warnings_json, status = 'draft'
                    """,
                    (
                        package.id, run_id, package.article_id, package.chunk.id, package.match.image.id, package.match.score,
                        json.dumps(package.match.reasons), int(package.match.is_fallback), package.theme, package.image_alt_text,
                        package.suggested_post_date.isoformat(), package.provider, package.model, json.dumps(warnings), _now(),
                    ),
                )
                self.conn.execute("DELETE FROM post_variants WHERE post_id = ?", (package.id,))
                for platform, post in package.platforms.items():
                    self.conn.execute(
                        """
                        INSERT INTO post_variants (post_id, platform, body, hashtags_json, alternate_hooks_json, char_count, suggested_post_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            package.id, platform, post.body, json.dumps(post.hashtags), json.dumps(post.alternate_hooks),
                            post.char_count, post.suggested_post_at,
                        ),
                    )
        except sqlite3.Error as exc:
            raise StorageError(f"save_package failed: {exc}") from exc

    _POST_SELECT = """
        SELECT p.*, a.title AS article_title, a.source_url AS article_url,
               i.path AS image_path, i.month AS image_month, i.year AS image_year, i.width AS image_width,
               i.height AS image_height, i.blur AS image_blur, i.subject AS image_subject,
               i.description AS image_description, i.alt_text AS image_alt, i.themes_json AS image_themes,
               i.moods_json AS image_moods,
               c.chunk_index, c.kind, c.heading AS chunk_heading, c.body AS chunk_body,
               c.themes_json AS chunk_themes, c.keywords_json AS chunk_keywords
        FROM generated_posts p
        JOIN articles a ON a.id = p.article_id
        JOIN images i ON i.id = p.image_id
        JOIN article_chunks c ON c.id = p.chunk_id
    """

    def _post_row_to_dict(self, r: sqlite3.Row) -> dict[str, Any]:
        variants = [
            {
                "platform": v["platform"],
                "body": v["body"],
                "hashtags": _loads(v["hashtags_json"], []),
                "alternate_hooks": _loads(v["alternate_hooks_json"], []),
                "char_count": v["char_count"],
                "suggested_post_at": v["suggested_post_at"],
                "edited_at": v["edited_at"],
                "published_url": v["published_url"],
            }
            for v in self.conn.execute("SELECT * FROM post_variants WHERE post_id = ? ORDER BY platform", (r["id"],))
        ]
        return {
            "id": r["id"],
            "run_id": r["run_id"],
            "status": r["status"],
            "suggested_post_date": r["suggested_post_date"],
            "theme": r["theme"],
            "image_alt_text": r["image_alt_text"],
            "match_score": r["match_score"],
            "match_reasons": _loads(r["match_reasons_json"], []),
            "is_fallback_image": bool(r["is_fallback_image"]),
            "warnings": _loads(r["warnings_json"], []),
            "provider": r["provider"],
            "model": r["model"],
            "created_at": r["created_at"],
            "reviewed_at": r["reviewed_at"],
            "notes": r["notes"],
            "article": {"id": r["article_id"], "title": r["article_title"], "source_url": r["article_url"]},
            "chunk": {
                "id": r["chunk_id"], "index": r["chunk_index"], "kind": r["kind"], "heading": r["chunk_heading"],
                "text": r["chunk_body"], "themes": _loads(r["chunk_themes"], []), "keywords": _loads(r["chunk_keywords"], []),
            },
            "image": {
                "id": r["image_id"], "path": r["image_path"], "month": r["image_month"], "year": r["image_year"],
                "width": r["image_width"], "height": r["image_height"], "blur": r["image_blur"],
                "subject": r["image_subject"], "description": r["image_description"], "alt_text": r["image_alt"],
                "themes": _loads(r["image_themes"], []), "moods": _loads(r["image_moods"], []),
            },
            "variants": variants,
        }

    def list_posts(self, *, article_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql = self._POST_SELECT + " WHERE 1=1"
        params: list[Any] = []
        if article_id:
            sql += " AND p.article_id = ?"
            params.append(article_id)
        if status:
            sql += " AND p.status = ?"
            params.append(status)
        sql += " ORDER BY p.suggested_post_date, c.chunk_index"
        try:
            return [self._post_row_to_dict(r) for r in self.conn.execute(sql, params).fetchall()]
        except sqlite3.Error as exc:
            raise StorageError(f"list_posts failed: {exc}") from exc

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(self._POST_SELECT + " WHERE p.id = ?", (post_id,)).fetchone()
        return self._post_row_to_dict(row) if row else None

    def list_articles(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT a.id, a.title, a.source_url, a.created_at, a.updated_at,
                   (SELECT COUNT(*) FROM generated_posts p WHERE p.article_id = a.id) AS posts,
                   (SELECT COUNT(*) FROM generated_posts p WHERE p.article_id = a.id AND p.status = 'approved') AS approved
            FROM articles a ORDER BY COALESCE(a.updated_at, a.created_at) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def update_post(
        self,
        post_id: str,
        *,
        status: str | None = None,
        suggested_post_date: str | None = None,
        notes: str | None = None,
        image_alt_text: str | None = None,
    ) -> dict[str, Any]:
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            if status not in ("draft", "approved", "scheduled", "published", "rejected"):
                raise StorageError(f"Invalid status {status!r}")
            sets += ["status = ?", "reviewed_at = ?"]
            params += [status, _now()]
        if suggested_post_date is not None:
            sets.append("suggested_post_date = ?")
            params.append(suggested_post_date)
        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)
        if image_alt_text is not None:
            sets.append("image_alt_text = ?")
            params.append(image_alt_text)
        if not sets:
            raise StorageError("Nothing to update")
        params.append(post_id)
        try:
            with self.conn:
                cur = self.conn.execute(f"UPDATE generated_posts SET {', '.join(sets)} WHERE id = ?", params)
                if cur.rowcount == 0:
                    raise StorageError(f"No post with id {post_id}")
                if suggested_post_date is not None:
                    # keep per-platform times on the new day
                    for v in self.conn.execute("SELECT id, suggested_post_at FROM post_variants WHERE post_id = ?", (post_id,)):
                        old = v["suggested_post_at"] or ""
                        if len(old) >= 10:
                            self.conn.execute(
                                "UPDATE post_variants SET suggested_post_at = ? WHERE id = ?",
                                (suggested_post_date + old[10:], v["id"]),
                            )
        except sqlite3.Error as exc:
            raise StorageError(f"update_post failed: {exc}") from exc
        post = self.get_post(post_id)
        assert post is not None
        return post

    def update_variant(self, post_id: str, platform: str, *, body: str, hashtags: list[str]) -> dict[str, Any]:
        tags = [t if t.startswith("#") else "#" + t.lstrip("#") for t in (h.strip() for h in hashtags) if t]
        full = body.strip() + ("\n\n" + " ".join(tags) if tags else "")
        try:
            with self.conn:
                cur = self.conn.execute(
                    "UPDATE post_variants SET body = ?, hashtags_json = ?, char_count = ?, edited_at = ? WHERE post_id = ? AND platform = ?",
                    (body.strip(), json.dumps(tags), len(full), _now(), post_id, platform),
                )
                if cur.rowcount == 0:
                    raise StorageError(f"No {platform} variant for post {post_id}")
        except sqlite3.Error as exc:
            raise StorageError(f"update_variant failed: {exc}") from exc
        post = self.get_post(post_id)
        assert post is not None
        return post

    def post_counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) AS n FROM generated_posts GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def set_post_status(self, post_id: str, status: str) -> None:
        self.update_post(post_id, status=status)
