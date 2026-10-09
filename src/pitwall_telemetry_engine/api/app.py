import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pitwall_telemetry_engine.api.routes import router
from pitwall_telemetry_engine.ingestion.timeline_replayer import session_cache

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm default session 9472 into memory cache on startup
    logger.info("Pre-warming active session 9472 into in-memory cache...")
    try:
        await session_cache.get(9472)
        logger.info("Session 9472 pre-warmed successfully.")
    except Exception as e:
        logger.warning("Could not pre-warm session 9472 on startup: %s", e)
    yield


# Create the FastAPI app
app = FastAPI(
    title="Pitwall Live Telemetry Engine",
    description="Broadcast-Grade 60 FPS F1 Telemetry & Digital Pit-Wall Engine",
    version="0.2.0",
    lifespan=lifespan,
)


# CORS middleware
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Static files directory for frontend
STATIC_DIR = Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "pitwall-telemetry-engine",
        "version": "0.2.0",
    }


@app.get("/")
def root():
    index_file = STATIC_DIR / "index.html"

    if index_file.exists():
        return FileResponse(index_file)
    return {
        "status": "online",
        "engine": "Pitwall v2 Telemetry Engine",
        "docs_url": "/docs",
    }


def start():
    is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"
    uvicorn.run(
        "pitwall_telemetry_engine.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=is_dev,
    )


if __name__ == "__main__":
    start()
