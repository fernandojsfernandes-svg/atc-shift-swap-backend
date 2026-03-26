import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")
# Render e outros hosts usam postgres://; SQLAlchemy 1.4+ exige postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Escolha explícita: psycopg (v3, por defeito), psycopg2, pg8000 (SSL puro; útil no Windows+Render)
# Ex.: DATABASE_DRIVER=pg8000 no .env
_DATABASE_DRIVER = os.environ.get("DATABASE_DRIVER", "").strip().lower()


def _prefer_psycopg3(url: str) -> str:
    if not url.startswith("postgresql://"):
        return url
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _strip_dialect(url: str) -> str:
    """Volta a postgresql:// sem +driver."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "+" in scheme:
        scheme = scheme.split("+", 1)[0]
    return f"{scheme}://{rest}"


def _apply_postgresql_driver(url: str) -> str:
    if _DATABASE_DRIVER == "pg8000":
        try:
            import pg8000  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "DATABASE_DRIVER=pg8000 requer: pip install pg8000"
            ) from e
        u = _strip_dialect(url)
        if u.startswith("postgresql://"):
            return u.replace("postgresql://", "postgresql+pg8000://", 1)
        return u
    if _DATABASE_DRIVER in ("psycopg2", "psycopg2-binary"):
        u = _strip_dialect(url)
        if u.startswith("postgresql+psycopg://"):
            u = u.replace("postgresql+psycopg://", "postgresql://", 1)
        return u
    # vazio ou psycopg: preferir psycopg3; normalizar se veio pg8000 no URL
    u = url
    if u.startswith("postgresql+pg8000://"):
        u = _strip_dialect(u)
    if u.startswith("postgresql+psycopg://"):
        return u
    return _prefer_psycopg3(u)


_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
elif DATABASE_URL.startswith("postgresql"):
    DATABASE_URL = _apply_postgresql_driver(DATABASE_URL)
    # Render Postgres: SSL obrigatório.
    if "sslmode" not in DATABASE_URL:
        sep = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"
    _connect_args["connect_timeout"] = 15
    if "gssencmode" not in DATABASE_URL and "render.com" in DATABASE_URL:
        sep = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL = f"{DATABASE_URL}{sep}gssencmode=disable"
    if "channel_binding" not in DATABASE_URL and "render.com" in DATABASE_URL:
        sep = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL = f"{DATABASE_URL}{sep}channel_binding=disable"

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
