import pytest
from openai import AuthenticationError
from pipeline import KnowledgeSyncPipeline

@pytest.fixture
def mock_pipeline_deps(mocker):
    # Mock scrape_articles
    mock_scrape = mocker.patch("pipeline.scrape_articles")
    mock_scrape.return_value = iter([
        {"title": "Article 1", "slug": "article-1", "updated_at": "v1"},
        {"title": "Article 2", "slug": "article-2", "updated_at": "v1"},
    ])
    
    # Mock convert_article
    mock_convert = mocker.patch("pipeline.convert_article")
    mock_convert.side_effect = ["/path/to/article-1.md", "/path/to/article-2.md"]
    
    # Mock upload_delta
    mock_upload = mocker.patch("pipeline.upload_delta")
    mock_upload.return_value = {"added": 2, "updated": 0, "skipped": 0, "errors": 0}
    
    # Mock load_state
    mock_load_state = mocker.patch("pipeline.load_state")
    mock_load_state.return_value = {}
    
    # Mock metrics push to prevent network calls
    mock_metrics_push = mocker.patch("pipeline.PipelineMetrics.push")
    
    return mock_scrape, mock_convert, mock_upload, mock_load_state, mock_metrics_push

def test_pipeline_run_success(mock_pipeline_deps):
    mock_scrape, mock_convert, mock_upload, mock_load_state, mock_metrics_push = mock_pipeline_deps
    
    pipeline = KnowledgeSyncPipeline(api_key="test-key", vector_store_id="vs_123")
    success = pipeline.run()
    
    assert success is True
    mock_scrape.assert_called_once()
    assert mock_convert.call_count == 2
    mock_upload.assert_called_once()
    mock_metrics_push.assert_called_once()

def test_pipeline_run_auth_failure(mock_pipeline_deps, mocker):
    mock_scrape, mock_convert, mock_upload, mock_load_state, mock_metrics_push = mock_pipeline_deps
    
    # Force authentication error during upload
    mock_upload.side_effect = AuthenticationError("Invalid Key", response=mocker.Mock(), body=None)
    
    pipeline = KnowledgeSyncPipeline(api_key="bad-key", vector_store_id="vs_123")
    success = pipeline.run()
    
    assert success is False
    mock_metrics_push.assert_called_once()

def test_pipeline_run_no_articles(mock_pipeline_deps):
    mock_scrape, mock_convert, mock_upload, mock_load_state, mock_metrics_push = mock_pipeline_deps
    
    # Return empty scrape
    mock_scrape.return_value = iter([])
    
    pipeline = KnowledgeSyncPipeline(api_key="test-key", vector_store_id="vs_123")
    success = pipeline.run()
    
    assert success is False
    mock_upload.assert_not_called()
    mock_metrics_push.assert_called_once()

def test_pipeline_run_partial_skip(mock_pipeline_deps, mocker):
    mock_scrape, mock_convert, mock_upload, mock_load_state, mock_metrics_push = mock_pipeline_deps

    # article-1 is already up to date (has a hash match), article-2 is new/changed.
    # article-1's existing .md is on disk — mock os.path.exists to confirm that.
    mock_load_state.return_value = {
        "article-1": {"hash": "v1"}
    }
    mocker.patch("pipeline.os.path.exists", return_value=True)
    mock_upload.return_value = {
        "added": 1, "updated": 0, "skipped": 1, "errors": 0,
        "files_embedded": 1, "chunks_embedded": 3,
    }

    pipeline = KnowledgeSyncPipeline(api_key="test-key", vector_store_id="vs_123")
    success = pipeline.run()

    assert success is True
    # Only article-2 should be converted
    assert mock_convert.call_count == 1
    # upload_delta receives both paths: the converted article-2 AND article-1's existing .md
    mock_upload.assert_called_once()
    args, kwargs = mock_upload.call_args
    assert len(kwargs["filepaths"]) == 2

def test_pipeline_run_all_skipped(mock_pipeline_deps, mocker):
    mock_scrape, mock_convert, mock_upload, mock_load_state, mock_metrics_push = mock_pipeline_deps

    # Both articles are up to date (hash matches)
    mock_load_state.return_value = {
        "article-1": {"hash": "v1"},
        "article-2": {"hash": "v1"},
    }
    # The existing .md files are on disk
    mocker.patch("pipeline.os.path.exists", return_value=True)
    # upload_delta is still called to verify remote existence; it reports all skipped
    mock_upload.return_value = {
        "added": 0, "updated": 0, "skipped": 2, "errors": 0,
        "files_embedded": 0, "chunks_embedded": 0,
    }

    pipeline = KnowledgeSyncPipeline(api_key="test-key", vector_store_id="vs_123")
    success = pipeline.run()

    # Pipeline should succeed; convert is never called; upload IS called (remote check)
    assert success is True
    mock_convert.assert_not_called()
    mock_upload.assert_called_once()
    mock_metrics_push.assert_called_once()
