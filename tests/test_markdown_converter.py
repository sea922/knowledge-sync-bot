import os
import pytest
from bs4 import BeautifulSoup
from converter.markdown import _clean_html, _fix_relative_links, _post_process, convert_article

def test_clean_html_noise_removal():
    html = """
    <div>
        <nav>Navigation</nav>
        <header>Header</header>
        <div class="breadcrumb">Breadcrumbs</div>
        <div class="feedback-widget">Was this helpful?</div>
        <main>
            <h1>Real Content</h1>
            <p>Important text.</p>
        </main>
        <footer>Footer</footer>
    </div>
    """
    soup = _clean_html(html)
    text = soup.get_text()
    
    assert "Real Content" in text
    assert "Important text." in text
    assert "Navigation" not in text
    assert "Header" not in text
    assert "Breadcrumbs" not in text
    assert "Was this helpful?" not in text
    assert "Footer" not in text

def test_fix_relative_links():
    html = """
    <div>
        <a href="/hc/en-us/articles/123">Link 1</a>
        <a href="https://other.com/link">Link 2</a>
        <img src="/hc/article_attachments/456/img.png" />
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    _fix_relative_links(soup)
    
    a_tags = soup.find_all("a")
    assert a_tags[0]["href"] == "https://support.optisigns.com/hc/en-us/articles/123"
    assert a_tags[1]["href"] == "https://other.com/link"
    
    img_tags = soup.find_all("img")
    assert img_tags[0]["src"] == "https://support.optisigns.com/hc/article_attachments/456/img.png"

def test_post_process():
    raw = "Line 1\n\n\n\nLine 2 \nLine 3  \n"
    processed = _post_process(raw)
    assert processed == "Line 1\n\nLine 2\nLine 3"

def test_convert_article(tmp_path):
    # tmp_path is a built-in pytest fixture for temporary directories
    article = {
        "title": "Test Guide",
        "html_url": "https://url.com/guide",
        "slug": "test-guide",
        "body_html": "<p>Here is some <strong>bold</strong> text.</p>"
    }
    
    output_dir = tmp_path / "articles"
    filepath = convert_article(article, str(output_dir))
    
    assert os.path.exists(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "# Test Guide" in content
    assert "> **Source:** https://url.com/guide" in content
    assert "Here is some **bold** text." in content
