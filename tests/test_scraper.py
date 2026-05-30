import pytest
import requests
from scraper.scraper import _slug_from_url, scrape_articles

def test_slug_from_url():
    assert _slug_from_url("https://support.optisigns.com/hc/en-us/articles/12345-some-title") == "some-title"
    assert _slug_from_url("https://support.optisigns.com/hc/en-us/articles/12345678-another-title") == "another-title"
    # Fallback to id if no slug
    assert _slug_from_url("https://support.optisigns.com/hc/en-us/articles/98765") == "98765"
    assert _slug_from_url("https://support.optisigns.com/hc/en-us/articles/98765/") == "98765"
    assert _slug_from_url("https://example.com/some-path") == "some-path"

def test_scrape_articles_success(mocker):
    # Mock requests.Session.get
    mock_get = mocker.patch("requests.Session.get")
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "articles": [
            {
                "id": 1,
                "title": "Test Article",
                "html_url": "https://support.optisigns.com/hc/en-us/articles/1-test-article",
                "body": "<p>Content</p>",
                "draft": False,
                "updated_at": "2023-01-01T00:00:00Z"
            },
            {
                "id": 2,
                "draft": True, # Should be skipped
                "title": "Draft Article",
                "html_url": "https://support.optisigns.com/hc/en-us/articles/2-draft",
                "body": "<p>Draft Content</p>",
                "updated_at": "2023-01-02T00:00:00Z"
            }
        ],
        "next_page": None
    }
    mock_get.return_value = mock_response
    
    articles = list(scrape_articles())
    
    assert len(articles) == 1
    assert articles[0]["title"] == "Test Article"
    assert articles[0]["slug"] == "test-article"
    assert articles[0]["body_html"] == "<p>Content</p>"
    assert articles[0]["updated_at"] == "2023-01-01T00:00:00Z"
    
    mock_get.assert_called_once()

def test_scrape_articles_pagination(mocker):
    mock_get = mocker.patch("requests.Session.get")
    
    # First page
    mock_resp1 = mocker.Mock()
    mock_resp1.json.return_value = {
        "articles": [
            {"id": 1, "title": "A1", "html_url": "https://url/1-a1", "body": "b1"}
        ],
        "next_page": "https://next-page.url"
    }
    
    # Second page
    mock_resp2 = mocker.Mock()
    mock_resp2.json.return_value = {
        "articles": [
            {"id": 2, "title": "A2", "html_url": "https://url/2-a2", "body": "b2"}
        ],
        "next_page": None
    }
    
    mock_get.side_effect = [mock_resp1, mock_resp2]
    
    # We also mock time.sleep to make test fast
    mocker.patch("time.sleep")
    
    articles = list(scrape_articles())
    
    assert len(articles) == 2
    assert mock_get.call_count == 2
    assert articles[1]["title"] == "A2"

def test_scrape_articles_error(mocker, caplog):
    mock_get = mocker.patch("requests.Session.get")
    mock_get.side_effect = requests.RequestException("Network Error")
    
    articles = list(scrape_articles())
    
    assert len(articles) == 0
    assert "Failed to fetch API page" in caplog.text
