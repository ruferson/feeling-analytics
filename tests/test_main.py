import sys
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from main import app, user_spotify_tokens

# Initialize FastAPI TestClient instance
client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_spotify_tokens():
    """Fixture to reset the in-memory token storage dictionary before each test."""
    user_spotify_tokens.clear()
    yield
    user_spotify_tokens.clear()


# ------------------------------------------------------------------------------
# Root and Login URL Tests
# ------------------------------------------------------------------------------


def test_read_root():
    """Test standard root endpoint response."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "feeling-analytics",
    }


@patch("main.SPOTIFY_CLIENT_ID", "test_client_id")
@patch("main.SPOTIFY_REDIRECT_URI", "http://localhost:3000/auth.html")
def test_get_spotify_login_url_success():
    """Test generation of Spotify OAuth authorization URL when client ID is present."""
    response = client.get("/auth/spotify/login-url")
    assert response.status_code == 200
    data = response.json()
    assert "authUrl" in data
    assert "client_id=test_client_id" in data["authUrl"]


@patch("main.SPOTIFY_CLIENT_ID", None)
def test_get_spotify_login_url_missing_client_id():
    """Test error handling when SPOTIFY_CLIENT_ID environment variable is missing."""
    response = client.get("/auth/spotify/login-url")
    assert response.status_code == 500
    assert (
        response.json()["detail"] == "SPOTIFY_CLIENT_ID is not configured in .env"
    )


# ------------------------------------------------------------------------------
# Account Link and Unlink Tests
# ------------------------------------------------------------------------------


def test_unlink_spotify_account():
    """Test removing stored tokens for a specific node ID."""
    user_spotify_tokens["node-123"] = {
        "access_token": "token_abc",
        "refresh_token": "token_xyz",
    }

    response = client.delete("/auth/spotify/node-123")
    assert response.status_code == 200
    assert response.json() == {"status": "unlinked", "nodeId": "node-123"}
    assert "node-123" not in user_spotify_tokens


@patch("requests.get")
@patch("requests.post")
def test_link_spotify_account_success(mock_post, mock_get):
    """Test successful OAuth token exchange and Spotify profile retrieval."""
    # Mock token exchange response from Spotify
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {
        "access_token": "mock_access_token",
        "refresh_token": "mock_refresh_token",
    }
    mock_post.return_value = mock_post_resp

    # Mock user profile response from Spotify
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "id": "spotify_user_999",
        "display_name": "Rubén",
    }
    mock_get.return_value = mock_get_resp

    payload = {"code": "valid_oauth_code"}
    response = client.post("/auth/spotify/node-123", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "spotifyAccountId": "spotify_user_999",
        "spotifyDisplayName": "Rubén",
    }
    assert user_spotify_tokens["node-123"] == {
        "access_token": "mock_access_token",
        "refresh_token": "mock_refresh_token",
    }


@patch("requests.post")
def test_link_spotify_account_failed_auth(mock_post):
    """Test error handling when Spotify token endpoint rejects authorization code."""
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 400
    mock_post.return_value = mock_post_resp

    payload = {"code": "invalid_code"}
    response = client.post("/auth/spotify/node-123", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Spotify authentication failed"


# ------------------------------------------------------------------------------
# Song Status Retrieval Tests
# ------------------------------------------------------------------------------


def test_get_node_song_no_tokens():
    """Test retrieving song status when no tokens exist for the specified node."""
    response = client.get("/nodes/node-123/song")
    assert response.status_code == 200
    assert response.json() == {
        "nodeId": "node-123",
        "song": "",
        "artist": "",
        "isPlaying": False,
        "synced": False,
        "spotifyPlayback": None,
    }


@patch("requests.get")
def test_get_node_song_currently_playing(mock_get):
    """Test retrieving active song info when user is currently playing music."""
    user_spotify_tokens["node-123"] = {
        "access_token": "valid_access_token",
        "refresh_token": "valid_refresh_token",
    }

    mock_spotify_data = {
        "is_playing": True,
        "item": {
          "name": "Starlight",
          "artists": [{"name": "Muse"}],
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_spotify_data
    mock_get.return_value = mock_resp

    response = client.get("/nodes/node-123/song")

    assert response.status_code == 200
    assert response.json() == {
        "nodeId": "node-123",
        "song": "Starlight",
        "artist": "Muse",
        "isPlaying": True,
        "synced": True,
        "spotifyPlayback": mock_spotify_data,
    }


@patch("requests.get")
def test_get_node_song_paused_or_idle(mock_get):
    """Test retrieving song status when playback is paused or inactive."""
    user_spotify_tokens["node-123"] = {
        "access_token": "valid_access_token",
        "refresh_token": "valid_refresh_token",
    }

    mock_spotify_data = {
        "is_playing": False,
        "item": None,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_spotify_data
    mock_get.return_value = mock_resp

    response = client.get("/nodes/node-123/song")

    assert response.status_code == 200
    assert response.json() == {
        "nodeId": "node-123",
        "song": "",
        "artist": "",
        "isPlaying": False,
        "synced": False,
        "spotifyPlayback": mock_spotify_data,
    }