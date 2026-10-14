"""FastAPI entry point for the Data Quality AI Assistant."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from routers import chat, data, nifi, spark, metadata, classification

app = FastAPI(title="Data Quality AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(chat.router)
app.include_router(nifi.router)
app.include_router(spark.router)
app.include_router(metadata.router)
app.include_router(classification.router)

@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve React build if it exists — mounted last so it doesn't shadow API routes
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=config.API_PORT,
        reload=True,
    )
