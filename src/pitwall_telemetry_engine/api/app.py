from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pitwall_telemetry_engine.api.routes import router

# Create the FastAPI app
app = FastAPI(
    title="Pitwall Live Telemetry Engine",
    description="Broadcast-Grade 60 FPS F1 Telemetry & Digital Pit-Wall Engine",
    version="0.2.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Static files directory for frontend
STATIC_DIR = Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
    uvicorn.run(
        "pitwall_telemetry_engine.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    start()
