import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI application with OpenAPI metadata
app = FastAPI(
    title="Feeling Analytics Service",
    description="Microservice for music metadata and sync animations",
    version="1.0.0",
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Define output response schema using Pydantic for validation
class SongInfoResponse(BaseModel):
    nodeId: str
    song: str
    artist: str
    bpm: int
    animationStyle: str
    synced: bool


# Health-check endpoint to verify microservice status
@app.get("/")
def read_root():
    return {"status": "ok", "service": "feeling-analytics"}


# Main endpoint called by NestJS via HttpService
@app.get("/nodes/{node_id}/song", response_model=SongInfoResponse)
def get_node_song(node_id: str):
    # Simulated metadata response for testing microservice integration
    return SongInfoResponse(
        nodeId=node_id,
        song="Midnight City",
        artist="M83",
        bpm=105,
        animationStyle="pulse_neon",
        synced=True,
    )


# Application entry point using Uvicorn ASGI server
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)