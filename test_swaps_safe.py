import requests
from datetime import date
import sys

BASE_URL = "http://127.0.0.1:8000"

USERS = [
    {"nome": "RUI PAGAIME", "email": "405541@atc.local", "password": "temp", "id": 1},
    {"nome": "BRUNO GUINCHO", "email": "405706@atc.local", "password": "temp", "id": 2},
    {"nome": "ANDRÉ CLETO", "email": "406082@atc.local", "password": "temp", "id": 3},
]

SHIFT_IDS = [1, 2, 3]  # Devem existir no mesmo dia no sistema

# Regras do sistema
INCOMPATIBLE_NEXT_DAY = [("T", "N"), ("Mt", "N")]
WORK_SHIFT_CODES = {"M", "T", "N", "MG", "Mt"}

def login_user(user):
    resp = requests.post(f"{BASE_URL}/users/login", json={
        "username": user["email"],  # campo é "username", valor é o email
        "password": user["password"]
    })
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")  # se o backend retornar token, usamos
    return {"Authorization": f"Bearer {token}"} if token else {}

def create_swaps(users, shift_ids):
    swap_ids = []
    shift_dates = []
    for user, shift_id in zip(users, shift_ids):
        headers = login_user(user)
        resp = requests.post(f"{BASE_URL}/swap-requests/", json={
            "shift_id": shift_id,
            "requester_id": user["id"],
            "accepter_id": None
        }, headers=headers)
        resp.raise_for_status()
        swap = resp.json()
        swap_ids.append(swap["id"])
        shift_dates.append(swap.get("shift", {}).get("data"))
        print(f"Swap criado: {swap}")
    return swap_ids, shift_dates

def check_swaps_valid(swap_ids, shift_dates):
    if len(set(shift_dates)) > 1:
        print("Erro: Swaps não estão todos no mesmo dia.")
        sys.exit(1)
    print(f"Todos os swaps válidos para o mesmo dia: {shift_dates[0]}")

def check_incompatibilities(users, shift_dates):
    # Simula verificação de incompatibilidade do dia seguinte
    print("Verificando incompatibilidades de dia seguinte...")
    for user in users:
        headers = login_user(user)
        resp = requests.get(f"{BASE_URL}/shifts/me", headers=headers)
        resp.raise_for_status()
        shifts = resp.json()
        # Para simplificação, apenas avisamos
        for s in shifts:
            for code_today, code_next in INCOMPATIBLE_NEXT_DAY:
                # Se houver match, avisa
                print(f"Aviso: Verifica turno {s['codigo']} para possíveis incompatibilidades no dia seguinte.")

def propose_cycle(swap_ids, user):
    headers = login_user(user)
    resp = requests.post(f"{BASE_URL}/swap-requests/cycles/propose", json=swap_ids, headers=headers)
    resp.raise_for_status()
    cycle = resp.json()
    print(f"Ciclo proposto: {cycle}")
    return cycle["cycle_id"]

def confirm_cycle(cycle_id, users):
    for user in users:
        headers = login_user(user)
        resp = requests.post(f"{BASE_URL}/swap-requests/cycles/{cycle_id}/confirm", headers=headers)
        resp.raise_for_status()
        print(f"{user['nome']} confirmou: {resp.json()}")

def check_shifts(user):
    headers = login_user(user)
    resp = requests.get(f"{BASE_URL}/shifts/me", headers=headers)
    resp.raise_for_status()
    shifts = resp.json()
    print(f"Shifts de {user['nome']}: {shifts}")

if __name__ == "__main__":
    print("=== Criar swaps ===")
    swap_ids, shift_dates = create_swaps(USERS, SHIFT_IDS)

    print("\n=== Verificar swaps válidos ===")
    check_swaps_valid(swap_ids, shift_dates)

    print("\n=== Verificar incompatibilidades ===")
    check_incompatibilities(USERS, shift_dates)

    print("\n=== Propor ciclo ===")
    cycle_id = propose_cycle(swap_ids, USERS[0])

    print("\n=== Confirmar ciclo por todos ===")
    confirm_cycle(cycle_id, USERS)

    print("\n=== Verificar shifts finais ===")
    for user in USERS:
        check_shifts(user)

    print("\n=== Teste completo concluído ===")