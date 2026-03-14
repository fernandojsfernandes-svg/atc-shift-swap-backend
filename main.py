import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base, SessionLocal
from models import ShiftType

from routers.teams import router as teams_router
from routers.users import router as users_router
from routers.schedules import router as schedules_router
from routers.shifts import router as shifts_router
from routers.swaps import router as swaps_router
from routers.notifications import router as notifications_router
from routers.importer import router as importer_router
from routers import dev


app = FastAPI()

# CORS: desenvolvimento (localhost) + produção (Vercel + FRONTEND_URL)
_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "https://atc-shift-swap-backend-6njjhahe7.vercel.app",
]
if os.environ.get("FRONTEND_URL"):
    _origins.append(os.environ.get("FRONTEND_URL").rstrip("/"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Resposta na raiz para não dar 404 ao abrir o URL da API no browser."""
    return {"message": "ATC Shift Swap API", "docs": "/docs"}


def create_shift_types():

    db = SessionLocal()

    codes = ["M", "T", "N", "MG", "Mt", "DC", "DS"]

    for code in codes:

        existing = db.query(ShiftType).filter(
            ShiftType.code == code
        ).first()

        if not existing:
            db.add(ShiftType(code=code))

    db.commit()
    db.close()


Base.metadata.create_all(bind=engine)

# Migrações opcionais só para SQLite (PostgreSQL usa create_all com modelos atualizados)
from database import DATABASE_URL as _db_url
if "sqlite" in _db_url:
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN DEFAULT 1"
            ))
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE shifts ADD COLUMN origin_status VARCHAR"))
            conn.commit()
    except Exception:
        pass

create_shift_types()


app.include_router(teams_router)
app.include_router(users_router)
app.include_router(schedules_router)
app.include_router(shifts_router)
app.include_router(swaps_router)
app.include_router(notifications_router)
app.include_router(importer_router)
app.include_router(dev.router)