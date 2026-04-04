from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.http import close_http_client
from app.api.routes import chat # Adjust based on your folder structure

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: The gateway is warming up ---
    yield
    # --- Shutdown: The gateway is closing ---
    await close_http_client()

app = FastAPI(title="LLM Gateway", lifespan=lifespan)

# Register routers
app.include_router(chat.router, prefix="/v1/chat")
