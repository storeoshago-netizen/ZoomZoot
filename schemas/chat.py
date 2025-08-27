from pydantic import BaseModel
from typing import List, Optional


class ChatRequest(BaseModel):
    sessionId: str
    message: str
    destination: Optional[str] = None
    days: Optional[int] = None
    preferences: Optional[List[str]] = None


class ChatResponse(BaseModel):
    message: str
    finished: bool
