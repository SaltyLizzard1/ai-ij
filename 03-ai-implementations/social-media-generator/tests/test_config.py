import os

from social_pipeline.config import Settings, load_dotenv


def test_dotenv_strips_inline_comments_and_keeps_quoted_hashes(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "MAX_BLUR=0.42                     # same cut-off your organiser uses\n"
        "IMAGE_ROOT=X:\\\n"
        "SKIP_FOLDERS=blurred,$RECYCLE.BIN,System Volume Information\n"
        "BRAND_VOICE=\"Warm. #nofilter\"\n"
        "# a full-line comment\n"
        "TIMEZONE = Asia/Bangkok\n",
        encoding="utf-8",
    )
    for key in ("MAX_BLUR", "IMAGE_ROOT", "SKIP_FOLDERS", "BRAND_VOICE", "TIMEZONE"):
        monkeypatch.delenv(key, raising=False)
    load_dotenv(env)
    assert os.environ["MAX_BLUR"] == "0.42"
    assert os.environ["IMAGE_ROOT"] == "X:\\"
    assert os.environ["SKIP_FOLDERS"] == "blurred,$RECYCLE.BIN,System Volume Information"
    assert os.environ["BRAND_VOICE"] == "Warm. #nofilter"
    assert os.environ["TIMEZONE"] == "Asia/Bangkok"
    settings = Settings.from_env(str(env))
    assert settings.max_blur == 0.42 and settings.timezone == "Asia/Bangkok"


def test_shipped_env_example_loads(tmp_path, monkeypatch):
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / ".env.example"
    for line in example.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            monkeypatch.delenv(line.split("=", 1)[0].strip(), raising=False)
    monkeypatch.setenv("BRAND_VOICE_FILE", "")  # not resolvable from tmp cwd; not needed here
    settings = Settings.from_env(str(example))
    assert settings.max_blur == 0.42
    assert settings.image_root == "X:\\"
    assert settings.platforms == ("facebook", "instagram", "linkedin", "x")
    assert settings.anthropic_server_fallbacks is True
