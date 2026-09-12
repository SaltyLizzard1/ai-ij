import json

from fastapi.testclient import TestClient

from social_pipeline import api as api_module
from social_pipeline.api import create_app
from social_pipeline.config import Settings
from social_pipeline.errors import ArticleLoadError
from social_pipeline.jobs import JobRunner
from social_pipeline.pipeline import RunOptions, SocialPipeline
from social_pipeline.llm.mock_provider import MockCaptionProvider
from social_pipeline.library.tagger import MockVisionTagger
from social_pipeline.sources.leaplog import LeapLogClient, portable_text_to_markdown
from tests.test_api import _wait

SITE = "https://www.quityourlifeandtravel.com"


def _block(text, style="normal", list_item=None, marks=None, mark_defs=None):
    return {"_type": "block", "style": style, "listItem": list_item, "markDefs": mark_defs or [],
            "children": [{"_type": "span", "text": text, "marks": marks or []}]}


BODY = [
    _block("The licence", style="h2"),
    _block("I arrived without a driving licence. I haven't had one since 2020. In Thailand, car and motorcycle licences are separate, so I started with the motorcycle licence."),
    _block("The basic cost is around 1,900 baht. You handle the process yourself and wait in the queues. I decided I wanted a little more hand-holding, so I asked around."),
    _block("Ask people who actually live here.", style="blockquote"),
    _block("What I learned", style="h2"),
    _block("Walk the neighbourhood first", list_item="bullet"),
    _block("Ask in two local groups what people pay", list_item="bullet"),
    _block("Say no to the first three places", list_item="bullet"),
    {"_type": "image", "asset": {"_ref": "x"}, "caption": "The view from the flat"},
    _block("I failed the practice test the first time, practiced like crazy, and passed the next day. Six weeks after landing I had a licence, a scooter and a mountain road I ride most Sunday mornings."),
    _block("bold and a link", marks=["strong", "lnk"], mark_defs=[{"_key": "lnk", "_type": "link", "href": "https://example.com"}]),
    {"_type": "callout", "text": "ignored widget"},
]

SANITY_POSTS = [
    {"_id": "b", "slug": "newest-post", "title": "Newest post", "publishedAt": "2026-09-01T08:00:00Z", "excerpt": "e2",
     "postType": "blog", "tags": ["thailand"], "body": BODY},
    {"_id": "a", "slug": "older-post", "title": "Older post", "publishedAt": "2026-06-10T08:00:00Z", "excerpt": "e1",
     "postType": "discussion", "tags": [], "body": BODY[:3]},
]

HARDCODED_HTML = """
<html><head><title>How to Move to Thailand in 60 Days | QYLAT</title></head><body>
<a href="/#the-leap-log">Back to The Leap Log</a>
<article><h1>How to Move to Thailand in 60 Days</h1>
<p>The first time I did this, it was easier. Not because it wasn't scary. It was terrifying. But I hadn't lost anything yet. I just knew I was done with the life I had and ready for something different.</p>
<p>So I left. Tested the waters. Bought a one-way ticket to Thailand and felt, for the first time in years, completely alive. It confirmed everything I suspected. This was the life I was supposed to be living.</p>
<blockquote class="border-l-4 not-prose"><p>There is no perfect moment. There is only the decision.</p></blockquote>
<div class="bg-emerald-50 not-prose"><p>Want the exact 60-day plan? Drop your email below and I'll send it straight to you.</p></div>
<p>Five years taught me what actually matters. I rebuilt. I came back stronger. And I would do every single bit of it again to get back to that feeling of being truly alive.</p>
</article><div class="comments">Comments here</div></body></html>
"""


def fake_client(**kw) -> LeapLogClient:
    def fetch_json(url):
        assert url == f"{SITE}/api/posts", url
        return SANITY_POSTS

    def fetch_text(url):
        assert url.endswith("/leap/how-to-move-to-thailand-in-60-days"), url
        return HARDCODED_HTML

    return LeapLogClient(fetch_json=fetch_json, fetch_text=fetch_text, **kw)


def test_portable_text_to_markdown():
    md = portable_text_to_markdown(BODY)
    assert md.startswith("## The licence\n\n")
    assert "> Ask people who actually live here." in md
    assert "- Walk the neighbourhood first\n- Ask in two local groups" in md
    assert "*[Photo: The view from the flat]*" in md
    assert "**[bold and a link](https://example.com)**" in md or "[**bold and a link**](https://example.com)" in md
    assert "ignored widget" not in md
    assert portable_text_to_markdown(None) == ""


def test_listing_matches_site_order_pinned_then_newest():
    arts = fake_client().list_articles()
    assert [a.slug for a in arts] == ["how-to-move-to-thailand-in-60-days", "newest-post", "older-post"]
    assert arts[0].pinned and arts[0].source == "site" and arts[0].published_date == "2026-03-15"
    assert arts[1].source == "sanity" and arts[1].url == f"{SITE}/leap/newest-post"


def test_listing_falls_back_to_sanity_cdn():
    calls = []

    def fetch_json(url):
        calls.append(url)
        if "/api/posts" in url:
            raise ArticleLoadError("site down", retryable=True)
        assert "zvvdrylu.apicdn.sanity.io" in url and "query=" in url
        return {"result": SANITY_POSTS}

    arts = LeapLogClient(fetch_json=fetch_json, fetch_text=lambda u: "").list_articles()
    assert len(calls) == 2 and [a.slug for a in arts][1:] == ["newest-post", "older-post"]


def test_fetch_article_sanity_and_hardcoded():
    c = fake_client()
    a = c.fetch_article("newest-post")
    assert a.source_format == "markdown" and a.title == "Newest post" and a.source_url == f"{SITE}/leap/newest-post"
    assert a.raw_content.startswith("# Newest post\n\n## The licence")

    h = c.fetch_article("how-to-move-to-thailand-in-60-days")
    assert h.source_format == "html" and h.title == "How to Move to Thailand in 60 Days"

    try:
        c.fetch_article("nope")
    except ArticleLoadError:
        pass
    else:
        raise AssertionError


def test_run_by_slug_end_to_end(settings, storage, monkeypatch):
    monkeypatch.setattr(Settings, "leaplog_client", lambda self, **kw: fake_client())
    pipe = SocialPipeline(settings, storage, MockCaptionProvider(), tagger=MockVisionTagger(), sleep=lambda s: None)
    res = pipe.run(RunOptions(slug="how-to-move-to-thailand-in-60-days", target_month=9, max_posts=3, write_output=False))
    assert res.status == "succeeded", res.errors
    assert res.article.source_url == f"{SITE}/leap/how-to-move-to-thailand-in-60-days"
    texts = " ".join(c["body"] for c in storage.conn.execute("SELECT body FROM article_chunks"))
    assert "Drop your email" not in texts and "Comments here" not in texts and "Back to The Leap Log" not in texts
    assert "no perfect moment" in texts  # blockquote survives the not-prose strip

    res2 = pipe.run(RunOptions(slug="newest-post", target_month=9, max_posts=2, write_output=False))
    assert res2.status == "succeeded" and res2.article.source_format == "markdown"


def test_api_leaplog_listing_and_run_by_slug(settings, monkeypatch):
    monkeypatch.setattr(Settings, "leaplog_client", lambda self, **kw: fake_client())
    c = TestClient(create_app(settings, jobs=JobRunner()))
    data = c.get("/api/leaplog").json()
    assert data["next_up"] == "how-to-move-to-thailand-in-60-days"
    assert [a["slug"] for a in data["articles"]][:2] == ["how-to-move-to-thailand-in-60-days", "newest-post"]
    assert data["articles"][0]["posts"] == 0

    job = _wait(c, c.post("/api/runs", json={"slug": "how-to-move-to-thailand-in-60-days", "month": 9, "max_posts": 2, "dry_run": True}).json()["id"])
    assert job["status"] == "succeeded", job
    data = c.get("/api/leaplog").json()
    first = data["articles"][0]
    assert first["posts"] == 2 and first["drafts"] == 2 and first["article_id"]
    assert data["next_up"] == "newest-post"
    assert c.post("/api/runs", json={"slug": "x", "url": "http://y"}).status_code == 400
