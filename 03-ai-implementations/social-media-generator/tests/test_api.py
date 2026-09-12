import time

from fastapi.testclient import TestClient

from social_pipeline.api import create_app
from social_pipeline.jobs import JobRunner
from tests.conftest import SAMPLE_ARTICLE


def _wait(client: TestClient, job_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _client(settings) -> TestClient:
    return TestClient(create_app(settings, jobs=JobRunner()))


def test_status_platforms_and_ui(settings):
    c = _client(settings)
    assert "Post Review" in c.get("/").text
    s = c.get("/api/status").json()
    assert s["provider"] == "mock" and s["images"]["total"] == 0
    assert set(c.get("/api/platforms").json()) >= {"linkedin", "x", "instagram", "facebook"}


def test_library_jobs_and_run_then_review_flow(settings):
    c = _client(settings)
    job = _wait(c, c.post("/api/library/scan", json={}).json()["id"])
    assert job["status"] == "succeeded" and job["result"]["total"] == 4

    job = _wait(c, c.post("/api/library/score", json={"months": ["2026-09"]}).json()["id"])
    assert job["status"] == "succeeded" and job["result"]["scored"] == 0  # fixture photos already scored

    r = c.post("/api/runs", json={"path": str(SAMPLE_ARTICLE), "month": 9, "max_posts": 3, "dry_run": True})
    assert r.status_code == 202
    job = _wait(c, r.json()["id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["posts"] == 3 and job["result"]["status"] == "succeeded"

    posts = c.get("/api/posts?status=draft").json()
    assert len(posts) == 3
    post = posts[0]
    assert post["image"]["path"] and post["variants"] and post["chunk"]["text"]
    assert c.get(f"/api/posts/{post['id']}").json()["id"] == post["id"]
    assert c.get("/api/articles").json()[0]["posts"] == 3

    # thumbnail + original file
    thumb = c.get(f"/api/images/{post['image']['id']}/thumb?w=120")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert c.get(f"/api/images/{post['image']['id']}/thumb?w=120").status_code == 200  # cached path
    assert c.get(f"/api/images/{post['image']['id']}/file").status_code == 200

    # edit a variant, reject over-limit edits
    r = c.put(f"/api/posts/{post['id']}/variants/x", json={"body": "Short and sweet.", "hashtags": ["chiangmai", "#travel"]})
    assert r.status_code == 200
    x = next(v for v in r.json()["variants"] if v["platform"] == "x")
    assert x["body"] == "Short and sweet." and x["hashtags"] == ["#chiangmai", "#travel"] and x["edited_at"]
    assert x["char_count"] == len("Short and sweet.\n\n#chiangmai #travel")
    r = c.put(f"/api/posts/{post['id']}/variants/x", json={"body": "x" * 300, "hashtags": []})
    assert r.status_code == 400
    assert c.put(f"/api/posts/{post['id']}/variants/tiktok", json={"body": "hi"}).status_code == 400

    # approve, move date, notes
    r = c.patch(f"/api/posts/{post['id']}", json={"status": "approved", "suggested_post_date": "2026-09-25", "notes": "good one"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved" and body["reviewed_at"] and body["notes"] == "good one"
    assert body["suggested_post_date"] == "2026-09-25"
    assert all(v["suggested_post_at"].startswith("2026-09-25T") for v in body["variants"])
    assert c.patch(f"/api/posts/{post['id']}", json={"status": "bogus"}).status_code == 400
    assert c.patch("/api/posts/nope", json={"status": "approved"}).status_code == 404

    counts = c.get("/api/status").json()["posts"]
    assert counts == {"draft": 2, "approved": 1}
    assert len(c.get("/api/posts?status=approved").json()) == 1

    # export approved for a publisher
    exp = c.get("/api/export?status=approved").json()
    assert exp["count"] == 1
    e = exp["posts"][0]
    assert e["image"]["path"].endswith(post["image"]["path"].split("/")[-1])
    assert e["platforms"]["x"]["text"].endswith("#chiangmai #travel")

    # reject + back to draft
    other = posts[1]
    assert c.patch(f"/api/posts/{other['id']}", json={"status": "rejected"}).json()["status"] == "rejected"
    assert c.patch(f"/api/posts/{other['id']}", json={"status": "draft"}).json()["status"] == "draft"


def test_run_validation_and_single_job_at_a_time(settings):
    c = _client(settings)
    assert c.post("/api/runs", json={}).status_code == 400
    assert c.post("/api/runs", json={"text": "x", "url": "http://a"}).status_code == 400
    assert c.post("/api/runs", json={"text": "# T\n\nbody", "platforms": ["myspace"]}).status_code == 400
    first = c.post("/api/library/scan", json={})
    second = c.post("/api/library/scan", json={})
    assert first.status_code == 202
    assert second.status_code in (202, 409)  # 409 if the first is still running
    _wait(c, first.json()["id"])


def test_run_job_reports_pipeline_failure(settings):
    c = _client(settings)
    job = _wait(c, c.post("/api/runs", json={"path": "/does/not/exist.md", "dry_run": True}).json()["id"])
    assert job["status"] == "failed" and "not found" in job["error"]
