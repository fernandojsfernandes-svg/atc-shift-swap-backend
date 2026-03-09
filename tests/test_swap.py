import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from main import app
from database import Base, get_db


# -----------------------------
# DATABASE DE TESTE (EM MEMÓRIA)
# -----------------------------
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


# -----------------------------
# TESTE COMPLETO DO CICLO DE SWAP
# -----------------------------
def test_full_swap_cycle():

    # Criar Team
    team = client.post("/teams/", json={"nome": "Team A"}).json()

    # Criar Users
    user1 = client.post("/users/", json={
        "nome": "User1",
        "email": "u1@test.com",
        "password": "123456",
        "team_id": team["id"]
    }).json()

    user2 = client.post("/users/", json={
        "nome": "User2",
        "email": "u2@test.com",
        "password": "123456",
        "team_id": team["id"]
    }).json()

    # LOGIN USER1
    login1 = client.post("/users/login", data={
        "username": "u1@test.com",
        "password": "123456"
    }).json()

    token1 = login1["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # LOGIN USER2
    login2 = client.post("/users/login", data={
        "username": "u2@test.com",
        "password": "123456"
    }).json()

    token2 = login2["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Criar Schedule
    schedule = client.post("/schedules/", json={
        "mes": 3,
        "ano": 2026,
        "team_id": team["id"]
    }).json()

    # Criar Shifts
    shift1 = client.post("/shifts/", json={
        "data": "2026-03-20",
        "codigo": "M",
        "user_id": user1["id"],
        "schedule_id": schedule["id"]
    }).json()

    shift2 = client.post("/shifts/", json={
        "data": "2026-03-20",
        "codigo": "T",
        "user_id": user2["id"],
        "schedule_id": schedule["id"]
    }).json()

    # Criar Swap (User1)
    swap = client.post(
        "/swap-requests/",
        json={"shift_id": shift1["id"]},
        headers=headers1
    ).json()

    # Aceitar Swap (User2)
    response = client.post(
        f"/swap-requests/{swap['id']}/accept",
        headers=headers2
    )

    assert response.status_code == 200

    # Confirmar troca
    shifts = client.get("/shifts/").json()

    shift1_updated = next(s for s in shifts if s["id"] == shift1["id"])
    shift2_updated = next(s for s in shifts if s["id"] == shift2["id"])

    assert shift1_updated["user_id"] == user2["id"]
    assert shift2_updated["user_id"] == user1["id"]