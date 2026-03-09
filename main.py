from fastapi import FastAPI
from database import engine, Base, SessionLocal
from models import ShiftType

from routers.teams import router as teams_router
from routers.users import router as users_router
from routers.schedules import router as schedules_router
from routers.shifts import router as shifts_router
from routers.swaps import router as swaps_router
from routers import dev


app = FastAPI()


def create_shift_types():
    db = SessionLocal()

    if db.query(ShiftType).count() == 0:
        db.add(ShiftType(code="M"))
        db.add(ShiftType(code="T"))
        db.add(ShiftType(code="N"))
        db.add(ShiftType(code="MG"))
        db.add(ShiftType(code="Mt"))
        db.add(ShiftType(code="DC"))
        db.add(ShiftType(code="DS"))

        db.commit()

    db.close()


Base.metadata.create_all(bind=engine)

create_shift_types()


app.include_router(teams_router)
app.include_router(users_router)
app.include_router(schedules_router)
app.include_router(shifts_router)
app.include_router(swaps_router)
app.include_router(dev.router)