import pytest
from pathlib import Path
from openai import AuthenticationError
from uploader.vector_store import upload_delta

@pytest.fixture
def mock_openai(mocker):
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = True
    
    # Mock upload_and_poll response
    mock_upload_resp = mocker.Mock()
    mock_upload_resp.id = "file_123"
    mock_client.vector_stores.files.upload_and_poll.return_value = mock_upload_resp
    
    mocker.patch("uploader.vector_store.openai.OpenAI", return_value=mock_client)
    return mock_client

@pytest.fixture
def temp_markdown(tmp_path):
    file1 = tmp_path / "article1.md"
    file1.write_text("content 1", encoding="utf-8")
    
    file2 = tmp_path / "article2.md"
    file2.write_text("content 2", encoding="utf-8")
    
    return [str(file1), str(file2)]

def test_upload_delta_success(mocker, mock_openai, temp_markdown):
    # Mock state
    mock_load = mocker.patch("uploader.vector_store._load_state", return_value={})
    mock_save = mocker.patch("uploader.vector_store._save_state")
    
    summary = upload_delta(
        filepaths=temp_markdown,
        vector_store_id="vs_123",
        updated_at_map={"article1": "v1", "article2": "v1"},
        openai_api_key="fake-key"
    )
    
    assert summary["added"] == 2
    assert summary["updated"] == 0
    assert summary["skipped"] == 0
    assert summary["errors"] == 0
    
    # Ensure save was called
    mock_save.assert_called_once()
    saved_state = mock_save.call_args[0][0]
    assert "article1" in saved_state
    assert saved_state["article1"]["file_id"] == "file_123"

def test_upload_delta_hash_cache(mocker, mock_openai, temp_markdown):
    # Setup state to simulate article1 being unchanged, article2 being changed
    existing_state = {
        "article1": {"hash": "v1", "file_id": "file_1"},
        "article2": {"hash": "v1", "file_id": "file_2"},
    }
    mocker.patch("uploader.vector_store._load_state", return_value=existing_state)
    mocker.patch("uploader.vector_store._save_state")
    
    updated_at_map = {
        "article1": "v1", # Unchanged
        "article2": "v2", # Changed
    }
    
    summary = upload_delta(
        filepaths=temp_markdown,
        vector_store_id="vs_123",
        updated_at_map=updated_at_map,
        openai_api_key="fake-key"
    )
    
    assert summary["added"] == 0
    assert summary["updated"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 0
    
    # Verify file deletion was called for article2
    mock_openai.vector_stores.files.delete.assert_called_once_with(
        vector_store_id="vs_123", file_id="file_2"
    )

def test_upload_delta_auth_error(mocker, temp_markdown):
    mock_client = mocker.Mock()
    mock_client.models.list.side_effect = AuthenticationError("Invalid Key", response=mocker.Mock(), body=None)
    mocker.patch("uploader.vector_store.openai.OpenAI", return_value=mock_client)
    
    with pytest.raises(AuthenticationError):
        upload_delta(
            filepaths=temp_markdown,
            vector_store_id="vs_123",
            openai_api_key="bad-key"
        )
