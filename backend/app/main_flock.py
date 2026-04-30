from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import flock_agent
from app.config import get_settings
from app.database import Base, SessionLocal, engine, migrate_sqlite_schema
from app.seed import seed_data

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title=f"{settings.app_name} Flock", lifespan=lifespan)
app.include_router(flock_agent.router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"name": f"{settings.app_name} Flock", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health")
def api_health():
    return {"status": "healthy"}
