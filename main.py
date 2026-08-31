import os
import requests
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

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
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:3000/auth.html")

user_spotify_tokens = {}

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
def read_root():
    return {"status": "ok", "service": "feeling-analytics"}

# Endpoint para devolver la URL de autenticación generada desde el backend
@app.get("/auth/spotify/login-url")
def get_spotify_login_url():
    if not SPOTIFY_CLIENT_ID:
        raise HTTPException(status_code=500, detail="SPOTIFY_CLIENT_ID no configurado en .env")

    scope = "user-read-currently-playing user-read-playback-state user-read-private"
    auth_url = (
        f"https://accounts.spotify.com/authorize?"
        f"client_id={SPOTIFY_CLIENT_ID}&"
        f"response_type=code&"
        f"redirect_uri={SPOTIFY_REDIRECT_URI}&"
        f"scope={scope}"
    )
    return {"authUrl": auth_url}

@app.delete("/auth/spotify/{node_id}")
def unlink_spotify_account(node_id: str):
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
        res = requests.post(token_url, data=body, timeout=10)
        if res.status_code != 200:
            raise HTTPException(status_code=400, detail="Error en la autenticación con Spotify")

        tokens = res.json()
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
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail="Spotify no está disponible") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/nodes/{node_id}/song", response_model=SongInfoResponse)
def get_node_song(node_id: str):
    tokens = user_spotify_tokens.get(node_id)

    if tokens and tokens.get("access_token"):
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        try:
            resp = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
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
                artist_name = item.get("artists", [{}])[0].get("name", "Unknown Artist")

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