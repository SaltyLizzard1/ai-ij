from social_pipeline.articles import detect_format, extract_title, load_article
from social_pipeline.chunker import chunk_article, hook_score, select_chunks
from social_pipeline.errors import ArticleLoadError, ChunkingError
from tests.conftest import SAMPLE_ARTICLE


def test_markdown_article_chunks_by_section_list_quote_and_hook():
    title, chunks = chunk_article(SAMPLE_ARTICLE.read_text(), "markdown", min_chars=120, max_chars=500, hook_chunks=2)
    assert title.startswith("90 days in Chiang Mai")
    kinds = {c.kind for c in chunks}
    assert {"section", "list", "quote", "hook"} <= kinds
    assert all(c.text for c in chunks)
    assert all(len(c.text) <= 500 * 1.3 for c in chunks if c.kind == "section")
    hooks = [c for c in chunks if c.kind == "hook"]
    assert len(hooks) == 2 and all(h.context for h in hooks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_html_article_strips_boilerplate_and_keeps_headings():
    html = """
    <html><body><nav><a href="/">Home</a></nav>
    <article><h1>Title here</h1>
    <h2>Part one</h2><p>%s</p><p>%s</p>
    <div class="share-buttons">Share this</div>
    <ul><li>First point about visas</li><li>Second point about banking</li></ul>
    </article><footer>copyright</footer></body></html>
    """ % ("First paragraph about moving abroad with a plan. " * 4, "Second paragraph on what it cost in time. " * 4)
    title, chunks = chunk_article(html, "html", min_chars=100, max_chars=400)
    assert title == "Title here"
    joined = " ".join(c.text for c in chunks)
    assert "Share this" not in joined and "copyright" not in joined and "Home" not in joined
    assert any(c.kind == "list" and "visas" in c.text for c in chunks)
    assert chunks[0].heading == "Part one"


def test_long_paragraph_is_split_on_sentences():
    para = " ".join(f"Sentence number {i} says something useful about the city." for i in range(40))
    _, chunks = chunk_article(para, "markdown", min_chars=100, max_chars=300, hook_chunks=0)
    assert len(chunks) > 3
    assert all(len(c.text) <= 300 for c in chunks)


def test_empty_article_raises():
    try:
        chunk_article("<html><body><nav>only nav</nav></body></html>", "html")
    except ChunkingError:
        pass
    else:
        raise AssertionError("expected ChunkingError")


def test_select_chunks_keeps_document_order():
    _, chunks = chunk_article(SAMPLE_ARTICLE.read_text(), "markdown", min_chars=120, max_chars=500)
    picked = select_chunks(chunks, 3)
    assert len(picked) == 3
    assert [c.index for c in picked] == sorted(c.index for c in picked)


def test_hook_score_prefers_specific_standalone_sentences():
    assert hook_score("I failed my motorcycle practice test the first time.") > hook_score("This was fine and it went okay.")
    assert hook_score("Short.") == 0.0


def test_detect_format_and_title():
    assert detect_format("<p>hello</p>") == "html"
    assert detect_format("# Hello\n\ntext") == "markdown"
    assert extract_title("# My Title\n\nbody", "markdown") == "My Title"
    assert extract_title("<h1>Head</h1>", "html") == "Head"


def test_load_article_requires_one_source():
    try:
        load_article()
    except ArticleLoadError:
        pass
    else:
        raise AssertionError
    art = load_article(text="# T\n\nSome body text here.")
    assert art.title == "T" and art.source_format == "markdown" and art.id
