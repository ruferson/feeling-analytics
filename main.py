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
DEFAULT_BPM = 120

user_spotify_tokens = {}

class SpotifyAuthRequest(BaseModel):
    code: str

class SongInfoResponse(BaseModel):
    nodeId: str
    song: str
    artist: str
    bpm: int
    bpmEstimated: bool
    isPlaying: bool
    animationStyle: str
    synced: bool
    spotifyPlayback: dict[str, Any] | None = None
    spotifyAudioFeatures: dict[str, Any] | None = None
    spotifyAudioAnalysis: dict[str, Any] | None = None
    audioFeaturesError: str | None = None

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

    # En main.py (FastAPI) dentro del endpoint de login-url o generación de scopes:
    scope = "user-read-currently-playing user-read-playback-state user-read-private"
    auth_url = (
        f"https://accounts.spotify.com/authorize?"
        f"client_id={SPOTIFY_CLIENT_ID}&"
        f"response_type=code&"
        f"redirect_uri={SPOTIFY_REDIRECT_URI}&"
        f"scope={scope}"
    )
    return {"authUrl": auth_url}

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
                        bpm=0,
                        bpmEstimated=False,
                        isPlaying=False,
                        animationStyle="pulse_neon",
                        synced=False,
                        spotifyPlayback=data,
                    )
                item = data.get("item", {})
                song_name = item.get("name", "Unknown Track")
                artist_name = item.get("artists", [{}])[0].get("name", "Unknown Artist")
                audio_features = None
                audio_analysis = None
                audio_features_error = None
                track_id = item.get("id")
                if track_id:
                    try:
                        audio_response = requests.get(
                            f"https://api.spotify.com/v1/audio-features/{track_id}",
                            headers=headers,
                            timeout=5,
                        )
                        if audio_response.ok:
                            audio_features = audio_response.json()
                        else:
                            audio_features_error = (
                                f"audio-features HTTP {audio_response.status_code}"
                            )
                    except requests.RequestException:
                        audio_features_error = "audio-features request failed"

                    if audio_features is None:
                        try:
                            analysis_response = requests.get(
                                f"https://api.spotify.com/v1/audio-analysis/{track_id}",
                                headers=headers,
                                timeout=5,
                            )
                            if analysis_response.ok:
                                audio_analysis = analysis_response.json()
                            else:
                                audio_features_error += (
                                    f"; audio-analysis HTTP {analysis_response.status_code}"
                                )
                        except requests.RequestException:
                            audio_features_error += "; audio-analysis request failed"

                tempo = None
                if audio_features:
                    tempo = audio_features.get("tempo")
                elif audio_analysis:
                    tempo = audio_analysis.get("track", {}).get("tempo")
                bpm_estimated = tempo is None or tempo <= 0

                return SongInfoResponse(
                    nodeId=node_id,
                    song=song_name,
                    artist=artist_name,
                    bpm=round(tempo) if not bpm_estimated else DEFAULT_BPM,
                    bpmEstimated=bpm_estimated,
                    isPlaying=True,
                    animationStyle="pulse_neon",
                    synced=True,
                    spotifyPlayback=data,
                    spotifyAudioFeatures=audio_features,
                    spotifyAudioAnalysis=audio_analysis,
                    audioFeaturesError=audio_features_error,
                )
        except Exception:
            pass

    return SongInfoResponse(
        nodeId=node_id,
        song="",
        artist="",
        bpm=0,
        bpmEstimated=False,
        isPlaying=False,
        animationStyle="pulse_neon",
        synced=False,
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)