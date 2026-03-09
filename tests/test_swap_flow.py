import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_full_swap_flow():

    # criar team
    team = client.post("/teams/", json={
        "nome": "TEAM_TEST"
    }).json()

    team_id = team["id"]

    # criar users
    user1 = client.post("/users/", json={
        "nome": "User1",
        "email": "user1_flow@test.com",
        "password": "123456",
        "team_id": team_id
    }).json()

    user2 = client.post("/users/", json={
        "nome": "User2",
        "email": "user2_flow@test.com",
        "password": "123456",
        "team_id": team_id
    }).json()

    # login user1
    login1 = client.post("/users/login", data={
        "username": "user1_flow@test.com",
        "password": "123456"
    }).json()

    token1 = login1["access_token"]

    # login user2
    login2 = client.post("/users/login", data={
        "username": "user2_flow@test.com",
        "password": "123456"
    }).json()

    token2 = login2["access_token"]

    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    # criar schedule
    schedule = client.post("/schedules/", json={
        "mes": 3,
        "ano": 2026,
        "team_id": team_id
    }).json()

    schedule_id = schedule["id"]

    # criar shifts
    shift1 = client.post("/shifts/", json={
        "user_id": user1["id"],
        "schedule_id": schedule_id,
        "data": "2026-03-25",
        "codigo": "M"
    }).json()

    shift2 = client.post("/shifts/", json={
        "user_id": user2["id"],
        "schedule_id": schedule_id,
        "data": "2026-03-25",
        "codigo": "T"
    }).json()

    # criar swap
    swap = client.post(
        "/swap-requests/",
        json={"shift_id": shift1["id"]},
        headers=headers1
    ).json()

    swap_id = swap["id"]

    # aceitar swap
    accept = client.post(
        f"/swap-requests/{swap_id}/accept",
        headers=headers2
    )

    assert accept.status_code == 200

    # verificar troca
    shifts = client.get("/shifts/").json()

    shift1_updated = next(s for s in shifts if s["id"] == shift1["id"])
    shift2_updated = next(s for s in shifts if s["id"] == shift2["id"])

    assert shift1_updated["user_id"] == user2["id"]
    assert shift2_updated["user_id"] == user1["id"]