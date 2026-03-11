# ATC Shift Swap Backend

## Estado atual do desenvolvimento

Últimas melhorias implementadas:
- guardar accepter_id no SwapRequest
- transação segura no accept_swap
- bloquear swaps passados
- evitar swaps duplicados
- endpoint /open não mostra swaps do próprio utilizador

## Objetivo
Backend para gestão de escalas e trocas de turnos entre controladores de tráfego aéreo.

Permite:
- autenticação de utilizadores
- gestão de turnos
- criação de pedidos de troca
- aceitação segura de swaps
- verificação de regras operacionais
- sugestões automáticas de trocas

---

# Stack Tecnológica

Backend framework:
FastAPI

ORM:
SQLAlchemy

Base de dados:
SQLite (desenvolvimento)

Autenticação:
JWT (JSON Web Tokens)

Servidor:
Uvicorn

---

# Estrutura do Projeto

---

# Modelos de Dados

Team  
User  
MonthlySchedule  
Shift  
SwapRequest  
SwapPreference  
ShiftType  

---

# Fluxo de Swaps

1. Utilizador cria pedido de troca para um dos seus turnos.

2. Outro utilizador aceita a troca.

3. O sistema valida:
- swap está OPEN
- utilizador não aceita o próprio swap
- existe turno no mesmo dia
- preferências de turno
- regras operacionais

4. A troca é executada de forma segura:

com transação SQLAlchemy.

---

# Regras Operacionais

Regras atuais:

Implementadas em:

---

# Endpoints Principais

Autenticação:

Swaps:

Turnos:

---

# Regras Importantes do Sistema

- Um utilizador não pode ter dois turnos no mesmo dia
- Não é possível criar swaps para turnos passados
- Não é possível aceitar o próprio swap
- Apenas um swap OPEN por turno
- A troca de turnos é feita dentro de uma transação segura
- Sequencias inválidas T e depois N; Mt e depois N (acisar utilizador antes de aprovar)
- máximo dias consecutivos a trabalhar:9 (avisar utilizador antres de aprovar)
-Controllers belong to a base operational team (A–E).  Each team has a default     monthly roster. Controllers normally follow the schedule of their assigned team.
However, shift swaps may result in controllers working shifts that were originally assigned to other teams.
The controller’s team membership does not change as a result of a swap.


---

# Estado Atual do Projeto

Backend funcional com:

- autenticação
- gestão de turnos
- criação de swaps
- aceitação segura de swaps
- validação de regras operacionais
- sugestões de trocas
- deteção de ciclos de swap

Sistema pronto para evolução futura.
---

# Development Status

Current state of the project:

Implemented:

- FastAPI backend
- JWT authentication
- User management
- Team management
- Monthly schedules
- Shift management
- Swap request creation
- Secure swap acceptance with transaction
- Operational rule validation (T→N, Mt→N)
- Swap preferences
- Swap suggestions
- Detection of 3-user swap cycles

Technical improvements implemented:

- accepter_id stored in SwapRequest
- SQLAlchemy relationships improved
- prevention of duplicate swaps
- prevention of swaps for past shifts
- filtering own swaps from open list
- transaction safety in swap acceptance

Project infrastructure:

- Git repository initialized
- GitHub repository created
- README.md created
- .gitignore configured
- PROJECT_CONTEXT.md created