from fastapi import APIRouter

router = APIRouter()

@router.post("/completions")
async def chat_completions():
    return {"message": "Not implemented yet"}
