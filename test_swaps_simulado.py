# test_swaps_simulado.py
# Script de teste completo com login simulado

from datetime import date

# Usuários de teste
USERS = [
    {"nome": "RUI PAGAIME", "id": 1},
    {"nome": "BRUNO GUINCHO", "id": 2},
    {"nome": "ANDRÉ CLETO", "id": 3},
]

# Swaps simulados (mesmo dia)
SHIFT_IDS = [1, 2, 3]
SHIFT_CODES = ["M", "T", "N"]  # turno de cada usuário
SWAP_STATUS_OPEN = "OPEN"

# Banco de dados simulado
shifts_db = {}
swaps_db = {}
cycles_db = {}
cycle_confirmations = {}

# 🔹 Login simulado
def login_user(user):
    # Retorna um "token" simulado (não é usado, só para consistência)
    return {"Authorization": f"Bearer SIMULADO_{user['id']}"}

# 🔹 Criar swaps
def create_swaps(users, shift_ids):
    swap_ids = []
    shift_dates = []
    today = date.today()
    for user, shift_id, code in zip(users, shift_ids, SHIFT_CODES):
        swap_id = len(swaps_db) + 1
        swaps_db[swap_id] = {
            "id": swap_id,
            "shift_id": shift_id,
            "requester_id": user["id"],
            "accepter_id": None,
            "status": SWAP_STATUS_OPEN,
            "date": today,
            "shift_code": code
        }
        shifts_db[shift_id] = {
            "shift_id": shift_id,
            "user_id": user["id"],
            "codigo": code,
            "date": today
        }
        swap_ids.append(swap_id)
        shift_dates.append(today)
        print(f"Swap criado: {swaps_db[swap_id]}")
    return swap_ids, shift_dates

# 🔹 Verificar swaps do mesmo dia
def check_swaps_valid(shift_dates):
    if len(set(shift_dates)) > 1:
        raise Exception("Erro: Swaps não estão todos no mesmo dia.")
    print(f"Todos os swaps válidos para o mesmo dia: {shift_dates[0]}")

# 🔹 Propor ciclo
def propose_cycle(swap_ids, user):
    cycle_id = len(cycles_db) + 1
    cycles_db[cycle_id] = {
        "id": cycle_id,
        "swaps": swap_ids.copy(),
        "status": "PROPOSED"
    }
    # Criar confirmações
    cycle_confirmations[cycle_id] = {u["id"]: False for u in USERS}
    print(f"Ciclo proposto: {cycles_db[cycle_id]}")
    return cycle_id

# 🔹 Confirmar ciclo
def confirm_cycle(cycle_id, users):
    for user in users:
        cycle_confirmations[cycle_id][user["id"]] = True
        print(f"{user['nome']} confirmou ciclo {cycle_id}")
    # Executar ciclo se todos confirmaram
    if all(cycle_confirmations[cycle_id].values()):
        execute_cycle(cycle_id)

# 🔹 Executar ciclo
def execute_cycle(cycle_id):
    swaps = cycles_db[cycle_id]["swaps"]
    # Rotacionar usuários nos shifts
    users = [swaps_db[s]["requester_id"] for s in swaps]
    rotated_users = users[-1:] + users[:-1]
    for swap_id, new_user in zip(swaps, rotated_users):
        shift_id = swaps_db[swap_id]["shift_id"]
        shifts_db[shift_id]["user_id"] = new_user
        swaps_db[swap_id]["status"] = "ACCEPTED"
    cycles_db[cycle_id]["status"] = "EXECUTED"
    print(f"Ciclo {cycle_id} executado com sucesso!")

# 🔹 Mostrar shifts finais
def check_shifts(users):
    for user in users:
        user_shifts = [s for s in shifts_db.values() if s["user_id"] == user["id"]]
        print(f"Shifts finais de {user['nome']}: {user_shifts}")

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