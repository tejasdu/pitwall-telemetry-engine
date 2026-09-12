from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from pitwall_telemetry_engine.api.routes import router

# Create the FastAPI app
app = FastAPI(
    title="Pitwall Live Telemetry Engine",
    description="Broadcast-Grade 60 FPS F1 Telemetry & Digital Pit-Wall Engine",
    version="0.2.0",
)

# Allow Cross-Origin Requests (CORS) for seamless local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include our REST API endpoints
app.include_router(router)

# Mount static files directory (where our HTML/CSS/JS frontend will live)
STATIC_DIR = Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount static assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def root():
    return {
        "status": "online",
        "engine": "Pitwall v2 Telemetry Engine",
        "docs_url": "/docs",
    }


def start():
    """CLI runner called by 'pitwall-web' or 'uv run pitwall-web'."""
    uvicorn.run(
        "pitwall_telemetry_engine.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    start()
