"""
Automated tests for cycle execution and validation.
Uses in-memory DB; cycle validation (same-day, T→N/Mt→N, max 9 days) is tested.
"""
import pytest
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import Base, get_db
from models import ShiftType


SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

# Seed shift types once for cycle tests (needed for validation)
_session = TestingSessionLocal()
for code in ["M", "T", "N", "MG", "Mt", "DC", "DS"]:
    if _session.query(ShiftType).filter(ShiftType.code == code).first() is None:
        _session.add(ShiftType(code=code))
_session.commit()
_session.close()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def _future_base(days_ahead=60):
    """Base date in the future so 'past shift' validation does not block tests."""
    return date.today() + timedelta(days=days_ahead)


def _login(user_id_suffix):
    r = client.post(
        "/users/login",
        data={"username": f"u{user_id_suffix}@cycle.test", "password": "123456"},
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _setup_three_users_same_day(schedule_id, team_id, base_date):
    """Create 3 users and 3 shifts on the same day (M, T, N). Returns (users, shifts)."""
    users = []
    for i in range(1, 4):
        u = client.post(
            "/users/",
            json={
                "nome": f"User{i}",
                "email": f"u{i}@cycle.test",
                "password": "123456",
                "employee_number": f"cycle{i}",
                "team_id": team_id,
            },
        ).json()
        users.append(u)
    shifts = []
    codes = ["M", "T", "N"]
    for i, u in enumerate(users):
        s = client.post(
            "/shifts/",
            json={
                "data": base_date.isoformat(),
                "codigo": codes[i],
                "user_id": u["id"],
                "schedule_id": schedule_id,
            },
        ).json()
        shifts.append(s)
    return users, shifts


# -----------------------------
# Cycle execution success
# -----------------------------
def test_cycle_execution_success():
    team = client.post("/teams/", json={"nome": "Team Cycle"}).json()
    schedule = client.post(
        "/schedules/",
        json={"mes": 3, "ano": 2026, "team_id": team["id"]},
    ).json()
    base = _future_base()
    users, shifts = _setup_three_users_same_day(schedule["id"], team["id"], base)

    swap_ids = []
    for i, (u, s) in enumerate(zip(users, shifts)):
        h = _login(i + 1)
        r = client.post("/swap-requests/", json={"shift_id": s["id"]}, headers=h)
        r.raise_for_status()
        swap_ids.append(r.json()["id"])

    r = client.post("/swap-requests/execute-cycle", json=swap_ids)
    assert r.status_code == 200, r.json()

    # Rotation: user0 gets shift2, user1 gets shift0, user2 gets shift1
    all_shifts = client.get("/shifts/").json()
    by_id = {s["id"]: s for s in all_shifts}
    assert by_id[shifts[0]["id"]]["user_id"] == users[2]["id"]
    assert by_id[shifts[1]["id"]]["user_id"] == users[0]["id"]
    assert by_id[shifts[2]["id"]]["user_id"] == users[1]["id"]


# -----------------------------
# Cycle validation: T→N forbidden
# -----------------------------
def test_cycle_validation_rejects_then_n():
    team = client.post("/teams/", json={"nome": "Team T-N"}).json()
    schedule = client.post(
        "/schedules/",
        json={"mes": 3, "ano": 2026, "team_id": team["id"]},
    ).json()
    base = _future_base()
    d0 = base           # B has T here (give to A)
    d1 = base + timedelta(days=1)   # A has N here (keep)
    d2 = base + timedelta(days=2)   # A gives here, C gives here

    # Cycle A->B->C->A: A gives d2, B gives d0 (T), C gives d2.
    # After: A gets B's T (d0) -> A has T on d0 + N on d1 = T→N (consecutive, forbidden).
    # No one gets two shifts same day: A has d0,d1; B has d2; C has d2 (one each).
    u1 = client.post(
        "/users/",
        json={"nome": "A", "email": "a@tn.test", "password": "123456", "employee_number": "a_tn", "team_id": team["id"]},
    ).json()
    u2 = client.post(
        "/users/",
        json={"nome": "B", "email": "b@tn.test", "password": "123456", "employee_number": "b_tn", "team_id": team["id"]},
    ).json()
    u3 = client.post(
        "/users/",
        json={"nome": "C", "email": "c@tn.test", "password": "123456", "employee_number": "c_tn", "team_id": team["id"]},
    ).json()

    s_a_d1 = client.post(
        "/shifts/",
        json={"data": d1.isoformat(), "codigo": "N", "user_id": u1["id"], "schedule_id": schedule["id"]},
    ).json()
    s_a_d2 = client.post(
        "/shifts/",
        json={"data": d2.isoformat(), "codigo": "M", "user_id": u1["id"], "schedule_id": schedule["id"]},
    ).json()
    s_b_d0 = client.post(
        "/shifts/",
        json={"data": d0.isoformat(), "codigo": "T", "user_id": u2["id"], "schedule_id": schedule["id"]},
    ).json()
    s_c_d2 = client.post(
        "/shifts/",
        json={"data": d2.isoformat(), "codigo": "MG", "user_id": u3["id"], "schedule_id": schedule["id"]},
    ).json()

    # Order for cycle: A gives d2, B gives d0, C gives d2 -> [swap_a_d2, swap_b_d0, swap_c_d2]
    login_a = client.post("/users/login", data={"username": "a@tn.test", "password": "123456"}).json()
    login_b = client.post("/users/login", data={"username": "b@tn.test", "password": "123456"}).json()
    login_c = client.post("/users/login", data={"username": "c@tn.test", "password": "123456"}).json()
    h_a = {"Authorization": f"Bearer {login_a['access_token']}"}
    h_b = {"Authorization": f"Bearer {login_b['access_token']}"}
    h_c = {"Authorization": f"Bearer {login_c['access_token']}"}

    def _post_swap(shift_id, headers):
        r = client.post("/swap-requests/", json={"shift_id": shift_id}, headers=headers)
        assert r.status_code == 200, f"Swap create failed: {r.status_code} {r.text}"
        return r.json()

    swap_a = _post_swap(s_a_d2["id"], h_a)
    swap_b = _post_swap(s_b_d0["id"], h_b)
    swap_c = _post_swap(s_c_d2["id"], h_c)
    cycle = [swap_a["id"], swap_b["id"], swap_c["id"]]

    r = client.post("/swap-requests/execute-cycle", json=cycle)
    assert r.status_code == 400
    detail = r.json().get("detail", "").lower()
    assert "forbidden" in detail or "sequence" in detail or ("t" in detail and "n" in detail)


# -----------------------------
# Cycle validation: max 9 consecutive working days
# -----------------------------
def test_cycle_validation_rejects_10_consecutive_working_days():
    team = client.post("/teams/", json={"nome": "Team 9"}).json()
    schedule = client.post(
        "/schedules/",
        json={"mes": 3, "ano": 2026, "team_id": team["id"]},
    ).json()
    # Base in the future; 12 consecutive days for A (1..11), B (12), C (1)
    base = _future_base()
    u1 = client.post(
        "/users/",
        json={"nome": "A9", "email": "a9@cycle.test", "password": "123456", "employee_number": "a9", "team_id": team["id"]},
    ).json()
    u2 = client.post(
        "/users/",
        json={"nome": "B9", "email": "b9@cycle.test", "password": "123456", "employee_number": "b9", "team_id": team["id"]},
    ).json()
    u3 = client.post(
        "/users/",
        json={"nome": "C9", "email": "c9@cycle.test", "password": "123456", "employee_number": "c9", "team_id": team["id"]},
    ).json()
    # A: days base+0 .. base+10 (give base+0). B: base+11 (give). C: base+0 (give).
    shifts_a = []
    for day in range(11):
        d = base + timedelta(days=day)
        s = client.post(
            "/shifts/",
            json={"data": d.isoformat(), "codigo": "M", "user_id": u1["id"], "schedule_id": schedule["id"]},
        ).json()
        shifts_a.append(s)
    s_b = client.post(
        "/shifts/",
        json={
            "data": (base + timedelta(days=11)).isoformat(),
            "codigo": "M",
            "user_id": u2["id"],
            "schedule_id": schedule["id"],
        },
    ).json()
    s_c = client.post(
        "/shifts/",
        json={
            "data": base.isoformat(),
            "codigo": "M",
            "user_id": u3["id"],
            "schedule_id": schedule["id"],
        },
    ).json()

    h1 = client.post("/users/login", data={"username": "a9@cycle.test", "password": "123456"}).json()
    h2 = client.post("/users/login", data={"username": "b9@cycle.test", "password": "123456"}).json()
    h3 = client.post("/users/login", data={"username": "c9@cycle.test", "password": "123456"}).json()
    headers = [
        {"Authorization": f"Bearer {h1['access_token']}"},
        {"Authorization": f"Bearer {h2['access_token']}"},
        {"Authorization": f"Bearer {h3['access_token']}"},
    ]

    def _post_swap(shift_id, h):
        r = client.post("/swap-requests/", json={"shift_id": shift_id}, headers=h)
        assert r.status_code == 200, f"Swap create failed: {r.status_code} {r.text}"
        return r.json()

    swap_a = _post_swap(shifts_a[0]["id"], headers[0])
    swap_b = _post_swap(s_b["id"], headers[1])
    swap_c = _post_swap(s_c["id"], headers[2])
    cycle = [swap_a["id"], swap_b["id"], swap_c["id"]]

    r = client.post("/swap-requests/execute-cycle", json=cycle)
    assert r.status_code == 400
    assert "9" in r.json().get("detail", "")


# -----------------------------
# Matching with wanted_options (cross-day)
# -----------------------------
def test_matching_uses_wanted_options():
    """GET /swap-requests/matching returns swaps when my shift matches wanted_options (day + type)."""
    team = client.post("/teams/", json={"nome": "Team Match"}).json()
    schedule = client.post(
        "/schedules/",
        json={"mes": 4, "ano": 2026, "team_id": team["id"]},
    ).json()
    base = _future_base()

    # A: turno dia base (oferece). B: turno dia base+1 tipo M (B é quem pode aceitar)
    u_a = client.post(
        "/users/",
        json={
            "nome": "Alice",
            "email": "alice@match.test",
            "password": "123456",
            "employee_number": "alice_m",
            "team_id": team["id"],
        },
    ).json()
    u_b = client.post(
        "/users/",
        json={
            "nome": "Bob",
            "email": "bob@match.test",
            "password": "123456",
            "employee_number": "bob_m",
            "team_id": team["id"],
        },
    ).json()

    shift_a = client.post(
        "/shifts/",
        json={
            "data": base.isoformat(),
            "codigo": "T",
            "user_id": u_a["id"],
            "schedule_id": schedule["id"],
        },
    ).json()
    shift_b = client.post(
        "/shifts/",
        json={
            "data": (base + timedelta(days=1)).isoformat(),
            "codigo": "M",
            "user_id": u_b["id"],
            "schedule_id": schedule["id"],
        },
    ).json()

    login_a = client.post("/users/login", data={"username": "alice@match.test", "password": "123456"}).json()
    h_a = {"Authorization": f"Bearer {login_a['access_token']}"}

    # Alice cria pedido: oferece turno dia base, quer dia base+1 M ou T
    r_swap = client.post(
        "/swap-requests/",
        json={
            "shift_id": shift_a["id"],
            "wanted_options": [
                {"date": (base + timedelta(days=1)).isoformat(), "shift_types": ["M", "T"]},
            ],
        },
        headers=h_a,
    )
    assert r_swap.status_code == 200
    swap = r_swap.json()

    # Bob chama matching: deve ver o pedido da Alice (ele tem M no dia base+1)
    login_b = client.post("/users/login", data={"username": "bob@match.test", "password": "123456"}).json()
    h_b = {"Authorization": f"Bearer {login_b['access_token']}"}
    r_matching = client.get("/swap-requests/matching", headers=h_b)
    assert r_matching.status_code == 200
    matching = r_matching.json()
    assert isinstance(matching, list)
    ids = [s["id"] for s in matching]
    assert swap["id"] in ids


# -----------------------------
# GET /cycles detects cross-day 2-way cycle (wanted_options)
# -----------------------------
def test_cycles_endpoint_detects_cross_day_two_way():
    """GET /swap-requests/cycles returns a 2-way cycle when A wants B's day and B wants A's day."""
    team = client.post("/teams/", json={"nome": "Team Cycles"}).json()
    schedule = client.post(
        "/schedules/",
        json={"mes": 5, "ano": 2026, "team_id": team["id"]},
    ).json()
    base = _future_base()
    d1 = base
    d2 = base + timedelta(days=1)

    u_a = client.post(
        "/users/",
        json={
            "nome": "CyA",
            "email": "cya@test.com",
            "password": "123456",
            "employee_number": "cya",
            "team_id": team["id"],
        },
    ).json()
    u_b = client.post(
        "/users/",
        json={
            "nome": "CyB",
            "email": "cyb@test.com",
            "password": "123456",
            "employee_number": "cyb",
            "team_id": team["id"],
        },
    ).json()

    shift_a = client.post(
        "/shifts/",
        json={"data": d1.isoformat(), "codigo": "T", "user_id": u_a["id"], "schedule_id": schedule["id"]},
    ).json()
    shift_b = client.post(
        "/shifts/",
        json={"data": d2.isoformat(), "codigo": "M", "user_id": u_b["id"], "schedule_id": schedule["id"]},
    ).json()

    login_a = client.post("/users/login", data={"username": "cya@test.com", "password": "123456"}).json()
    login_b = client.post("/users/login", data={"username": "cyb@test.com", "password": "123456"}).json()
    h_a = {"Authorization": f"Bearer {login_a['access_token']}"}
    h_b = {"Authorization": f"Bearer {login_b['access_token']}"}

    # A oferece d1, quer d2 M. B oferece d2, quer d1 T → ciclo A↔B
    r1 = client.post(
        "/swap-requests/",
        json={
            "shift_id": shift_a["id"],
            "wanted_options": [{"date": d2.isoformat(), "shift_types": ["M"]}],
        },
        headers=h_a,
    )
    assert r1.status_code == 200
    swap_a = r1.json()

    r2 = client.post(
        "/swap-requests/",
        json={
            "shift_id": shift_b["id"],
            "wanted_options": [{"date": d1.isoformat(), "shift_types": ["T"]}],
        },
        headers=h_b,
    )
    assert r2.status_code == 200
    swap_b = r2.json()

    r_cycles = client.get("/swap-requests/cycles")
    assert r_cycles.status_code == 200
    data = r_cycles.json()
    assert "cycles" in data
    cycles = data["cycles"]
    assert len(cycles) >= 1
    # each item is {"cycle": {"cycle": [id, ...], "message": "..."}, "message": "..."}
    cycle_ids = {frozenset(c["cycle"]["cycle"]) for c in cycles}
    assert frozenset({swap_a["id"], swap_b["id"]}) in cycle_ids
