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