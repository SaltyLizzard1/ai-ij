from social_pipeline.keywords import analyse_chunk_text, detect_moods, detect_themes, extract_keywords
from social_pipeline.library.matcher import ImageMatcher, month_distance
from social_pipeline.models import Chunk, ImageAsset, ImageTags


def test_keywords_and_themes_from_text():
    text = "I started with the motorcycle licence. The scooter is how this city moves, and the mountain road is quiet on Sundays."
    kws = extract_keywords(text, "The licence")
    assert any("licence" in k for k in kws)
    themes = detect_themes(text)
    assert "transport_road" in themes
    assert "mountains" in themes
    assert "calm" in detect_moods("It was quiet and peaceful, a slow morning.")
    out = analyse_chunk_text("Absolutely.", "Test", context="We celebrated the milestone at a night market with friends.")
    assert "celebratory" in out["moods"] or "celebration" in out["themes"]


def _img(id_, month, themes, moods, keywords, blur=0.3, subject="thing", used=0):
    return ImageAsset(
        id=id_, path=f"2026-{month:02d}/{id_}.jpg", file_name=f"{id_}.jpg", month=month, year=2026, width=4000, height=3000,
        blur=blur, used_count=used,
        tags=ImageTags(subject=subject, description="", keywords=keywords, themes=themes, moods=moods, alt_text=""),
    )


def test_matcher_prefers_shared_theme_then_month_then_sharpness():
    chunk = Chunk(0, "section", "The licence", "scooter licence story", keywords=["scooter", "licence"], themes=["transport_road"], moods=["calm"])
    scooter_aug = _img("a", 8, ["transport_road"], ["calm"], ["scooter", "road"], subject="red scooter")
    market_sep = _img("b", 9, ["markets_shopping"], ["energetic"], ["market"])
    scooter_sep_blurry = _img("c", 9, ["transport_road"], ["calm"], ["scooter"], blur=0.41)
    scooter_sep_sharp = _img("d", 9, ["transport_road"], ["calm"], ["scooter"], blur=0.2)
    ranked = ImageMatcher().rank(chunk, [scooter_aug, market_sep, scooter_sep_blurry, scooter_sep_sharp], target_month=9)
    assert [m.image.id for m in ranked][:2] == ["d", "c"]
    assert ranked[0].score > ranked[-1].score
    assert any("themes: transport_road" in r for r in ranked[0].reasons)
    # theme beats month: the August scooter outranks the September market
    ids = [m.image.id for m in ranked]
    assert ids.index("a") < ids.index("b")


def test_matcher_strict_month_excludes_and_reuse_penalises():
    chunk = Chunk(0, "section", None, "x", themes=["transport_road"])
    fresh = _img("fresh", 9, ["transport_road"], [], [])
    reused = _img("reused", 9, ["transport_road"], [], [], used=3)
    other_month = _img("aug", 8, ["transport_road"], [], [])
    ranked = ImageMatcher(strict_month=True).rank(chunk, [fresh, reused, other_month], target_month=9)
    assert [m.image.id for m in ranked] == ["fresh", "reused"]


def test_matcher_fallback_to_untagged_and_unsuitable_skipped():
    chunk = Chunk(0, "section", None, "x", themes=["food_drink"])
    unsuitable = _img("u", 9, ["food_drink"], [], [])
    unsuitable.tags.suitable_for_social = False
    untagged = ImageAsset(id="n", path="2026-09/n.jpg", file_name="n.jpg", month=9, blur=0.1)
    best = ImageMatcher().best(chunk, [unsuitable, untagged], target_month=9)
    assert best.image.id == "n" and best.is_fallback


def test_month_distance_wraps():
    assert month_distance(12, 1) == 1
    assert month_distance(3, 9) == 6
