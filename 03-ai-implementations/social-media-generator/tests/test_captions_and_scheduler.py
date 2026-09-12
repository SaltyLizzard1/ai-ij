from datetime import date

import pytest

from social_pipeline.captions import CaptionGenerator, CaptionRules, build_schema, build_system_prompt
from social_pipeline.errors import CaptionGenerationError
from social_pipeline.llm.base import JSONRequest, LLMResult
from social_pipeline.llm.mock_provider import MockCaptionProvider
from social_pipeline.models import Chunk, ImageAsset, ImageMatch, ImageTags
from social_pipeline.scheduler import ScheduleConfig, platform_post_at, suggest_post_date, target_window
from social_pipeline.utils import with_retries


def _match():
    img = ImageAsset("i", "2026-09/a.jpg", "a.jpg", 9, 2026, 4000, 3000, 0.3,
                     tags=ImageTags("scooter", "A scooter.", ["scooter"], ["transport_road"], ["calm"], "A red scooter"))
    return ImageMatch(img, 4.0, ["themes: transport_road"])


class ScriptedProvider:
    """Returns canned outputs in order; used to test corrective retries."""

    name = "scripted"
    model_name = "scripted-1"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests: list[JSONRequest] = []

    def complete_json(self, request):
        self.requests.append(request)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return LLMResult(data=out, provider=self.name, model=self.model_name)


def _post(body, tags=()):
    return {"body": body, "hashtags": list(tags), "alternate_hooks": ["a", "b", "c", "d"]}


def test_schema_and_prompt_include_platform_rules():
    schema = build_schema(["x", "facebook"])
    assert set(schema["required"]) == {"x", "facebook", "image_alt_text", "theme"}
    prompt = build_system_prompt(CaptionRules("Voice", forbid_financial_figures=True, allow_hashtags=False, banned_phrases=("unlock",)), ["x"])
    assert "280 characters" in prompt and "No financial figures" in prompt and "No hashtags" in prompt and "unlock" in prompt


def test_violations_trigger_one_corrective_round_then_autofix():
    bad = {"x": _post("Hook — with a dash " + "and a very long body. " * 20, ["#a", "#b", "#c"]), "image_alt_text": "alt", "theme": "t"}
    still_bad = {"x": _post("Still — has a dash but short now.", ["#a"]), "image_alt_text": "alt", "theme": "t"}
    provider = ScriptedProvider([bad, still_bad])
    gen = CaptionGenerator(provider, CaptionRules("v"), ["x"], sleep=lambda s: None)
    result = gen.generate("T", Chunk(0, "section", None, "text"), _match())
    assert len(provider.requests) == 2
    assert "PREVIOUS ATTEMPT" in provider.requests[1].user
    assert "—" not in result.posts["x"].body
    assert result.posts["x"].char_count <= 280
    assert any("replaced dashes" in w for w in result.warnings)


def test_retry_on_retryable_error_then_success():
    ok = {"x": _post("Fine post."), "image_alt_text": "alt", "theme": "t"}
    provider = ScriptedProvider([CaptionGenerationError("rate limited", retryable=True), ok])
    gen = CaptionGenerator(provider, CaptionRules("v"), ["x"], max_retries=3, sleep=lambda s: None)
    result = gen.generate("T", Chunk(0, "section", None, "text"), _match())
    assert result.posts["x"].body == "Fine post." and len(provider.requests) == 2


def test_non_retryable_error_propagates():
    provider = ScriptedProvider([CaptionGenerationError("refused", retryable=False)])
    gen = CaptionGenerator(provider, CaptionRules("v"), ["x"], sleep=lambda s: None)
    with pytest.raises(CaptionGenerationError):
        gen.generate("T", Chunk(0, "section", None, "text"), _match())


def test_with_retries_gives_up_after_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise CaptionGenerationError("boom", retryable=True)

    with pytest.raises(CaptionGenerationError):
        with_retries(fn, attempts=3, sleep=lambda s: None)
    assert len(calls) == 3


def test_mock_provider_respects_no_hashtags():
    gen = CaptionGenerator(MockCaptionProvider(), CaptionRules("v", allow_hashtags=False), ["instagram"], sleep=lambda s: None)
    result = gen.generate("T", Chunk(0, "section", None, "First sentence. Second one.", keywords=["k"]), _match())
    assert result.posts["instagram"].hashtags == []


def test_target_window_rules():
    today = date(2026, 9, 12)
    assert target_window(9, today) == (date(2026, 9, 13), date(2026, 9, 30))
    assert target_window(11, today) == (date(2026, 11, 1), date(2026, 11, 30))
    assert target_window(3, today)[0] == date(2026, 9, 13)  # past month posts now by default
    assert target_window(3, today, seasonal=True) == (date(2027, 3, 1), date(2027, 3, 31))
    assert target_window(9, date(2026, 9, 30))[0] == date(2027, 9, 1)  # last day rolls over


def test_posts_spread_across_weekdays_with_platform_hours():
    cfg = ScheduleConfig("Asia/Bangkok", weekdays_only=True, start_from=date(2026, 9, 12))
    days = [suggest_post_date(9, i, 4, cfg) for i in range(4)]
    assert days == sorted(days) and len(set(days)) == 4
    assert all(d.weekday() < 5 for d in days)
    assert platform_post_at(days[0], "facebook", cfg).endswith("T19:00:00+07:00")
    assert platform_post_at(days[0], "linkedin", cfg).endswith("T08:00:00+07:00")


def test_bad_timezone_is_reported():
    with pytest.raises(ValueError):
        suggest_post_date(9, 0, 1, ScheduleConfig("Mars/Olympus"))
