import json
from pathlib import Path

from social_pipeline.library.scanner import LibraryScanner, _record_key, load_quality_records
from social_pipeline.library.tagger import MockVisionTagger, prepare_image, select_tag_candidates
from social_pipeline.llm.mock_provider import MockCaptionProvider
from social_pipeline.models import ImageTags
from social_pipeline.pipeline import RunOptions, SocialPipeline
from social_pipeline.storage import Storage
from tests.conftest import SAMPLE_ARTICLE


def test_record_key_normalises_windows_paths():
    assert _record_key("X:/2026-03\\20260311_102047.jpg") == "2026-03/20260311_102047.jpg"
    assert _record_key("G:\\My Drive\\2026-09\\IMG.JPG") == "2026-09/img.jpg"


def test_scanner_joins_quality_records_and_skips_blurred_folder(library):
    lib, records = library
    assets = LibraryScanner(lib, records_dir=records, skip_folders=("blurred",)).scan()
    paths = {a.path for a in assets}
    assert "2026-09/IMG_scooter.jpg" in paths and "blurred/IMG_bad.jpg" not in paths
    scooter = next(a for a in assets if a.file_name == "IMG_scooter.jpg")
    assert scooter.month == 9 and scooter.year == 2026 and scooter.blur == 0.30 and scooter.quality_source == "records"
    assert scooter.width == 4000 and scooter.orientation == "landscape"
    assert load_quality_records(None) == {}


def test_scanner_reads_dimensions_when_no_record(tmp_path):
    from tests.conftest import make_library

    lib, _ = make_library(tmp_path, {"2026-07": {"x.jpg": 0.1}})
    assets = LibraryScanner(lib, records_dir=None).scan()
    assert assets[0].quality_source == "none" and assets[0].width == 120 and assets[0].height == 90


def test_tag_candidates_filter_blur_and_prefer_target_month(library):
    lib, records = library
    assets = LibraryScanner(lib, records_dir=records).scan()
    cands = select_tag_candidates(assets, target_month=9, max_blur=0.42, limit=10)
    names = [c.file_name for c in cands]
    assert "IMG_blurry.jpg" not in names
    assert names[:2] == ["IMG_market.jpg", "IMG_scooter.jpg"]  # September first, sharpest first
    assert names[-1] == "IMG_mountain.jpg"


def test_prepare_image_downscales_to_jpeg(library):
    lib, _ = library
    data, media = prepare_image(lib / "2026-09" / "IMG_scooter.jpg", max_edge=50)
    assert media == "image/jpeg" and data[:2] == b"\xff\xd8"


def test_storage_roundtrip_tags_and_usage(settings, library):
    lib, records = library
    with Storage(settings.db_path) as st:
        assets = LibraryScanner(lib, records_dir=records).scan()
        ins, upd = st.upsert_images(assets)
        assert ins == 4 and upd == 0
        ins, upd = st.upsert_images(assets)
        assert ins == 0 and upd == 4
        img = st.list_images(months=[9])[0]
        st.save_tags(img.id, ImageTags("scooter", "d", ["scooter", "road"], ["transport_road"], ["calm"], "alt"))
        st.mark_image_used(img.id)
        again = st.get_image(img.id)
        assert again.tags.subject == "scooter" and again.used_count == 1
        assert again.tags.themes == ["transport_road"]
        tags = st.conn.execute("SELECT tag FROM image_tags WHERE image_id = ? ORDER BY tag", (img.id,)).fetchall()
        assert [t[0] for t in tags] == ["calm", "road", "scooter", "scooter", "transport_road"]
        assert st.image_stats()["tagged"] == 1


def test_pipeline_end_to_end_with_mocks(settings, storage, tmp_path):
    tagger = MockVisionTagger({"subject": "scooter on a street", "keywords": ["scooter", "licence", "road"], "themes": ["transport_road"], "moods": ["calm"]})
    pipe = SocialPipeline(settings, storage, MockCaptionProvider(), tagger=tagger, sleep=lambda s: None)
    result = pipe.run(RunOptions(path=str(SAMPLE_ARTICLE), target_month=9, max_posts=3, output_path=str(tmp_path / "out.json")))

    assert result.status == "succeeded", result.errors
    assert result.chunks_total > 3 and len(result.packages) == 3
    assert result.images_tagged == 3  # the three sharp photos; blurry one skipped
    assert tagger.calls == 3
    used = [p.match.image.path for p in result.packages]
    assert len(set(used)) == 3  # no photo reused within a run
    for pkg in result.packages:
        assert set(pkg.platforms) == {"linkedin", "x", "instagram", "facebook"}
        assert pkg.platforms["x"].char_count <= 280
        assert pkg.suggested_post_date.month == 9 and pkg.suggested_post_date.year == 2026
        assert pkg.platforms["facebook"].suggested_post_at.endswith("+07:00")

    data = json.loads(Path(result.output_path).read_text(encoding="utf-8"))
    assert data["status"] == "succeeded" and len(data["posts"]) == 3
    post = data["posts"][0]
    assert {"chunk", "image", "platforms", "suggested_post_date", "image_alt_text"} <= set(post)
    assert post["image"]["path"].startswith("2026-0")
    assert post["platforms"]["linkedin"]["full_text"]

    # persisted
    posts = storage.list_posts(article_id=result.article.id)
    assert len(posts) == 3 and all(len(p["variants"]) == 4 for p in posts)
    assert storage.get_image(result.packages[0].match.image.id).used_count == 1
    run = storage.conn.execute("SELECT status FROM pipeline_runs").fetchone()[0]
    assert run == "succeeded"

    # second run on the same article is idempotent for chunks and upserts posts
    result2 = pipe.run(RunOptions(path=str(SAMPLE_ARTICLE), target_month=9, max_posts=3, write_output=False))
    assert result2.status == "succeeded"
    assert storage.conn.execute("SELECT COUNT(*) FROM article_chunks").fetchone()[0] == result2.chunks_total


def test_pipeline_isolates_caption_failures(settings, storage):
    from social_pipeline.errors import CaptionGenerationError

    class FlakyProvider(MockCaptionProvider):
        def complete_json(self, request):
            if "licence" in request.payload["chunk_text"].lower():
                raise CaptionGenerationError("refused", retryable=False)
            return super().complete_json(request)

    pipe = SocialPipeline(settings, storage, FlakyProvider(), tagger=MockVisionTagger(), sleep=lambda s: None)
    result = pipe.run(RunOptions(path=str(SAMPLE_ARTICLE), target_month=9, max_posts=4, write_output=False))
    assert result.status == "partial"
    assert result.errors and result.packages
    assert storage.conn.execute("SELECT status FROM pipeline_runs").fetchone()[0] == "partial"


def test_pipeline_without_tagger_uses_fallback_images(settings, storage):
    pipe = SocialPipeline(settings, storage, MockCaptionProvider(), tagger=None, sleep=lambda s: None)
    result = pipe.run(RunOptions(path=str(SAMPLE_ARTICLE), target_month=9, max_posts=2, write_output=False))
    assert result.status == "succeeded"
    assert all(p.match.is_fallback for p in result.packages)
    assert result.images_tagged == 0


def test_pipeline_reuses_photos_when_chunks_outnumber_them(settings, storage):
    pipe = SocialPipeline(settings, storage, MockCaptionProvider(), tagger=MockVisionTagger(), sleep=lambda s: None)
    result = pipe.run(RunOptions(path=str(SAMPLE_ARTICLE), target_month=9, max_posts=6, write_output=False))
    assert result.status == "succeeded", result.errors
    assert len(result.packages) == 6 > 4  # only 4 photos in the fixture library
    assert any("reused within this run" in r for p in result.packages for r in p.match.reasons)
