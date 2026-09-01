import os
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="Feeling Analytics Service",
    description="Microservice for music metadata and sync animations",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI",
    "http://localhost:3000/auth.html",
)

user_spotify_tokens: dict[str, dict[str, str | None]] = {}


class SpotifyAuthRequest(BaseModel):
    code: str


class SongInfoResponse(BaseModel):
    nodeId: str
    song: str
    artist: str
    isPlaying: bool
    animationStyle: str
    synced: bool
    spotifyPlayback: dict[str, Any] | None = None


class SpotifyAccountResponse(BaseModel):
    spotifyAccountId: str
    spotifyDisplayName: str | None = None


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "service": "feeling-analytics"}


@app.get("/auth/spotify/login-url")
def get_spotify_login_url() -> dict[str, str]:
    if not SPOTIFY_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="SPOTIFY_CLIENT_ID is not configured in .env",
        )

    scope = "user-read-currently-playing user-read-playback-state user-read-private"
    auth_url = (
        "https://accounts.spotify.com/authorize?"
        f"client_id={SPOTIFY_CLIENT_ID}&"
        "response_type=code&"
        f"redirect_uri={SPOTIFY_REDIRECT_URI}&"
        f"scope={scope}"
    )
    return {"authUrl": auth_url}


@app.delete("/auth/spotify/{node_id}")
def unlink_spotify_account(node_id: str) -> dict[str, str]:
    user_spotify_tokens.pop(node_id, None)
    return {"status": "unlinked", "nodeId": node_id}


@app.post("/auth/spotify/{node_id}", response_model=SpotifyAccountResponse)
def link_spotify_account(node_id: str, payload: SpotifyAuthRequest):
    token_url = "https://accounts.spotify.com/api/token"
    body = {
        "grant_type": "authorization_code",
        "code": payload.code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }

    try:
        response = requests.post(token_url, data=body, timeout=10)
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Spotify authentication failed",
            )

        tokens = response.json()
        user_spotify_tokens[node_id] = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
        }

        profile = requests.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10,
        )
        profile.raise_for_status()
        profile_data = profile.json()
        return SpotifyAccountResponse(
            spotifyAccountId=profile_data["id"],
            spotifyDisplayName=profile_data.get("display_name"),
        )
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Spotify is unavailable",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/nodes/{node_id}/song", response_model=SongInfoResponse)
def get_node_song(node_id: str) -> SongInfoResponse:
    tokens = user_spotify_tokens.get(node_id)

    if tokens and tokens.get("access_token"):
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        try:
            response = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers=headers,
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                if not data.get("is_playing") or not data.get("item"):
                    return SongInfoResponse(
                        nodeId=node_id,
                        song="",
                        artist="",
                        isPlaying=False,
                        animationStyle="pulse_neon",
                        synced=False,
                        spotifyPlayback=data,
                    )

                item = data.get("item", {})
                song_name = item.get("name", "Unknown Track")
                artist_name = item.get("artists", [{}])[0].get(
                    "name",
                    "Unknown Artist",
                )

                return SongInfoResponse(
                    nodeId=node_id,
                    song=song_name,
                    artist=artist_name,
                    isPlaying=True,
                    animationStyle="pulse_neon",
                    synced=True,
                    spotifyPlayback=data,
                )
        except Exception:
            pass

    return SongInfoResponse(
        nodeId=node_id,
        song="",
        artist="",
        isPlaying=False,
        animationStyle="pulse_neon",
        synced=False,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
