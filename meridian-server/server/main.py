from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from server.db import init_db
from server.otlp import router as otlp_router
from server.api.runs import router as runs_router
from server.api.spans import router as spans_router
from server.api.cost import router as cost_router
from server.api.alerts import router as alerts_router
from server.api.regression import router as regression_router
from server.alerts.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Meridian", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(otlp_router)
app.include_router(ws_router)
app.include_router(runs_router,   prefix="/api")
app.include_router(spans_router,  prefix="/api")
app.include_router(cost_router,   prefix="/api")
app.include_router(alerts_router,     prefix="/api")
app.include_router(regression_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8001")),
        reload=True,
    )
