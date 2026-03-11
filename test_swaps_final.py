# test_swaps_final.py
import requests
from datetime import date

BASE_URL = "http://127.0.0.1:8000"

# Usuários reais
USERS = [
    {"nome": "RUI PAGAIME", "email": "405541@atc.local", "password": "temp", "id": 1},
    {"nome": "BRUNO GUINCHO", "email": "405706@atc.local", "password": "temp", "id": 2},
    {"nome": "ANDRÉ CLETO", "email": "406082@atc.local", "password": "temp", "id": 3},
]

# Shift IDs válidos do mesmo dia (25/03/2026)
SHIFT_IDS = [1, 2, 3]

# 🔹 Login real e obter token
def login_user(user):
    resp = requests.post(f"{BASE_URL}/users/login", data={
        "username": user["email"],
        "password": user["password"]
    })
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise Exception(f"Login falhou para {user['nome']}")
    return token

# 🔹 Criar swaps
def create_swaps(users, shift_ids):
    swap_ids = []
    shift_dates = []
    for user, shift_id in zip(users, shift_ids):
        token = login_user(user)
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(f"{BASE_URL}/swap-requests/", json={
            "shift_id": shift_id,
            "acceptable_shift_types": ["M", "T", "N"]
        }, headers=headers)
        resp.raise_for_status()
        swap = resp.json()
        swap_ids.append(swap["id"])
        shift_dates.append(swap.get("shift", {}).get("data"))
        print(f"Swap criado: {swap}")
    return swap_ids, shift_dates

# 🔹 Verificar swaps do mesmo dia
def check_swaps_valid(shift_dates):
    if len(set(shift_dates)) > 1:
        raise Exception("Erro: Swaps não estão todos no mesmo dia.")
    print(f"Todos os swaps válidos para o mesmo dia: {shift_dates[0]}")

# 🔹 Propor ciclo
def propose_cycle(swap_ids, user):
    token = login_user(user)
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{BASE_URL}/swap-requests/cycles/propose", json=swap_ids, headers=headers)
    resp.raise_for_status()
    cycle = resp.json()
    print(f"Ciclo proposto: {cycle}")
    return cycle["cycle_id"]

# 🔹 Confirmar ciclo
def confirm_cycle(cycle_id, users):
    for user in users:
        token = login_user(user)
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(f"{BASE_URL}/swap-requests/cycles/{cycle_id}/confirm", headers=headers)
        resp.raise_for_status()
        print(f"{user['nome']} confirmou: {resp.json()}")

# 🔹 Mostrar shifts finais
def check_shifts(users):
    for user in users:
        token = login_user(user)
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/shifts/me", headers=headers)
        resp.raise_for_status()
        shifts = resp.json()
        print(f"Shifts de {user['nome']}: {shifts}")

# === Fluxo principal ===
if __name__ == "__main__":
    print("=== Criar swaps ===")
    swap_ids, shift_dates = create_swaps(USERS, SHIFT_IDS)

    print("\n=== Verificar swaps válidos ===")
    check_swaps_valid(shift_dates)

    print("\n=== Propor ciclo ===")
    cycle_id = propose_cycle(swap_ids, USERS[0])

    print("\n=== Confirmar ciclo por todos ===")
    confirm_cycle(cycle_id, USERS)

    print("\n=== Verificar shifts finais ===")
    check_shifts(USERS)

    print("\n=== Teste completo concluído ===")