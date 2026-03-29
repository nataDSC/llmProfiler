from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import chat

app = FastAPI(title="LLM Gateway & Profiler")

# Register routers
app.include_router(chat.router, prefix="/v1/chat")
