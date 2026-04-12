import logging
import os
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.http import close_http_client
from app.api.routes import chat # Adjust based on your folder structure
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from app.middleware.metrics import metrics_middleware
from app.middleware.pii import PIISanitizerMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: The gateway is warming up ---
    yield
    # --- Shutdown: The gateway is closing ---
    await close_http_client()


app = FastAPI(title="LLM Gateway", lifespan=lifespan)


# Register PII sanitizer middleware (before metrics)
app.add_middleware(PIISanitizerMiddleware)
app.middleware("http")(metrics_middleware)

# Register routers
app.include_router(chat.router, prefix="/v1/chat")

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
