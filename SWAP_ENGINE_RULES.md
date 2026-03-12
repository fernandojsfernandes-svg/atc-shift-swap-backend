# Swap Engine Rules

Rules for detecting and executing shift swaps between Air Traffic Controllers. The engine must keep resulting schedules operationally valid.

---

## Types of swaps

### Direct swap (most common)

Two controllers exchange shifts. Usually same day; may be different days (e.g. “I give day 5, you give day 12”).

- Example: A has morning 12 Mar, B has evening 12 Mar → after swap, A has evening, B has morning.
- Flow: one user offers a shift; the other accepts (must have a shift to give in return, respecting day/type rules). Both must confirm.

### Multi-user cycle

Three or more controllers form a cycle: A offers S1 and wants S2, B offers S2 and wants S3, C offers S3 and wants S1 → A→B→C→A.

- Can be **same day** (three shifts on one date) or **cross-day** (e.g. A gives day 1, B gives day 5, C gives day 10).
- Each request must express “what I offer” and “what I want” (e.g. a specific shift, or options: “day 7 M or T; day 8 T; day 11 T, M or MG”).
- Engine detects compatible cycles, **alerts** users (“possible 3-way swap on these dates”), then **each user must confirm** before execution.

---

## Swap detection logic

- Each swap request = “user offers shift X, wants shift Y” (or set of acceptable (date, type) options).
- Model as a directed graph (e.g. offered shift → wanted shift or matching request).
- Engine: load pending requests → build graph → detect cycles (including N-way and cross-day) → validate constraints → propose cycle → collect confirmations → simulate → validate again → execute or reject.

---

## Operational constraints (all must hold)

1. **Ownership** – Controller only offers shifts they currently own.
2. **One shift per day** – No controller may end up with two shifts on the same day.
3. **Forbidden sequences** – No T→N or Mt→N next-day (warn user; can allow with explicit confirm). Other pairs may be added later.
4. **Max 9 consecutive working days** – Working = M, T, N, MG, Mt; DC/DS are rest. Reject if swap would exceed 9.
5. **Single use** – A shift participates in at most one swap (or one cycle) in a given execution.
6. **Atomic execution** – For a cycle, either all swaps in the cycle are applied or none (no partial execution).

---

## Validation process

1. Detect potential cycle (graph cycle detection).
2. **Simulate** the swap (compute resulting assignment per user).
3. **Validate** all constraints on the simulated schedule (one per day, no T→N/Mt→N, max 9 days).
4. If valid → execute (update shift ownership, update swap status) in a single transaction.
5. If invalid → reject cycle and report reason (e.g. “would exceed 9 consecutive days for user X”).

---

## Behaviour

- **Safety first:** Never produce an illegal schedule.
- **Fairness:** All involved users must confirm before execution.
- If no valid swap is possible, leave schedules unchanged and inform the user.

---

## Confirmation and history

- Every swap (direct or cycle) requires confirmation from all parties. No “record only” without the other side accepting.
- Swap history is kept (`SwapHistory`); can be listed via `GET /swap-requests/history` e limpo/arquivado mensalmente via `DELETE /swap-requests/history?before=YYYY-MM-DD`.
- Quando novas escalas são re-importadas, o histórico é usado para marcar em `Shift` eventuais inconsistências (troca aceite ainda não refletida no PDF), para que o utilizador possa confirmar com o serviço de escalas.
