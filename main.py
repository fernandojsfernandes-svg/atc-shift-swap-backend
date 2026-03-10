from fastapi import FastAPI
from database import engine, Base, SessionLocal
from models import ShiftType

from routers.teams import router as teams_router
from routers.users import router as users_router
from routers.schedules import router as schedules_router
from routers.shifts import router as shifts_router
from routers.swaps import router as swaps_router
from routers.importer import router as importer_router
from routers import dev


app = FastAPI()


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

create_shift_types()


app.include_router(teams_router)
app.include_router(users_router)
app.include_router(schedules_router)
app.include_router(shifts_router)
app.include_router(swaps_router)
app.include_router(importer_router)
app.include_router(dev.router)