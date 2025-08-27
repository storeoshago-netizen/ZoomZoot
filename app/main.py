from fastapi import FastAPI
from core.cors import add_cors
from app.api.v1.chat import router as chat_router

app = FastAPI(title="ZoomZoot Travel Planner API")

# Add CORS middleware
add_cors(app)

# Include API routes
app.include_router(chat_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "ZoomZoot Travel Planner API"}
