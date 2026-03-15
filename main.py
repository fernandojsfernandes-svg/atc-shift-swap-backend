import os
from dotenv import load_dotenv
load_dotenv()

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
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


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    try:
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        # No Render, usar o URL público no Swagger "Try it out"
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
        if render_url:
            openapi_schema["servers"] = [{"url": render_url}]
        app.openapi_schema = openapi_schema
    except Exception:
        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
    return app.openapi_schema


app.openapi = _custom_openapi

# CORS: desenvolvimento (localhost) + produção (Vercel + Render docs + FRONTEND_URL)
_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "https://atc-shift-swap-backend-6njjhahe7.vercel.app",
    "https://atc-shift-swap-backend.onrender.com",
]
if os.environ.get("FRONTEND_URL"):
    _origins.append(os.environ.get("FRONTEND_URL").rstrip("/"))
# Regex: localhost + *.onrender.com (Swagger) + *.vercel.app (frontend Vercel)
_origin_regex = (
    r"^https?://("
    r"(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?"
    r"|([a-zA-Z0-9-]+\.)*onrender\.com"
    r"|([a-zA-Z0-9-]+\.)*vercel\.app"
    r")(/.*)?$"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.head("/")
def root():
    """Resposta na raiz para não dar 404 ao abrir o URL da API no browser. HEAD para health check do Render."""
    return {"message": "ATC Shift Swap API", "docs": "/docs"}


def _cors_headers_for_request(request: Request) -> dict:
    """Cabeçalhos CORS para anexar a respostas de erro (evitar 'CORS missing' no browser)."""
    origin = request.headers.get("origin")
    headers = {}
    if origin and (origin in _origins or origin.rstrip("/") in _origins):
        headers["Access-Control-Allow-Origin"] = origin
    headers["Access-Control-Allow-Credentials"] = "true"
    return headers


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler_with_cors(request: Request, exc: StarletteHTTPException):
    """Garante que 4xx/5xx do FastAPI tenham CORS."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_cors_headers_for_request(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler_with_cors(request: Request, exc: RequestValidationError):
    """Garante que 422 de validação tenham CORS."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers=_cors_headers_for_request(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Garante que respostas 500 tenham CORS para o frontend poder ler a mensagem."""
    logging.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_cors_headers_for_request(request),
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

# Migrações opcionais só para SQLite (PostgreSQL usa create_all com modelos atualizados)
from database import DATABASE_URL as _db_url
if "sqlite" in _db_url:
    from sqlalchemy import text
    _migrations = [
        "ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN DEFAULT 1",
        "ALTER TABLE shifts ADD COLUMN origin_status VARCHAR",
        "ALTER TABLE shifts ADD COLUMN color_bucket VARCHAR",
        "ALTER TABLE shifts ADD COLUMN inconsistency_flag BOOLEAN DEFAULT 0",
        "ALTER TABLE shifts ADD COLUMN inconsistency_message VARCHAR",
    ]
    for sql in _migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
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