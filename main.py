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

# Permitir chamadas do frontend (localhost:5173 ou telemóvel na mesma rede em PC_IP:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"^http://(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):5173$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

# Adicionar coluna notifications_enabled a users se não existir (SQLite)
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN DEFAULT 1"
        ))
        conn.commit()
except Exception:
    pass  # coluna já existe ou BD não é SQLite

create_shift_types()


app.include_router(teams_router)
app.include_router(users_router)
app.include_router(schedules_router)
app.include_router(shifts_router)
app.include_router(swaps_router)
app.include_router(notifications_router)
app.include_router(importer_router)
app.include_router(dev.router)