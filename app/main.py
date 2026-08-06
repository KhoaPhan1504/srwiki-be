from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import auth, profile


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SR-WIKI API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(profile.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
