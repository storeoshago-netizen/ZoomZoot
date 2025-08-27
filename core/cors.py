from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings


def add_cors(app: FastAPI):
    # Parse configured origins (comma-separated) and normalize
    origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

    # Add common local/dev origins so browsers opening local files or dev servers
    # can talk to the API during development.
    dev_origins = [
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    for o in dev_origins:
        if o not in origins:
            origins.append(o)

    # Ensure we have at least one origin. Keep credentials enabled for auth flows.
    if not origins:
        origins = ["http://localhost:8000"]

    # For local development allow all origins but disable credentials when using wildcard.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        # Allow all common methods/headers for development preflights
        allow_methods=["*"],
        allow_headers=["*"],
    )
