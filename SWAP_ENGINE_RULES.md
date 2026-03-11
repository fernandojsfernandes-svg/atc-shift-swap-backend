# Swap Engine Rules

This document defines the rules used by the swap engine to detect and execute valid shift swaps between Air Traffic Controllers.

The swap engine must always ensure that the resulting schedules remain operationally valid.

---

# Types of Swaps

The system must support different types of exchanges.

## Direct Swap (Most Common)

Two controllers exchange shifts on the same day.

Example:

Controller A
Has: Morning shift (12 March)
Wants: Evening shift (12 March)

Controller B
Has: Evening shift (12 March)
Wants: Morning shift (12 March)

Swap result:

A ↔ B

This is expected to represent the majority of swap requests.

---

## Multi-User Swap Cycle

Less frequently, swaps may involve multiple controllers across different days.

Example:

Controller A
Offers: Shift S1
Wants: Shift S2

Controller B
Offers: Shift S2
Wants: Shift S3

Controller C
Offers: Shift S3
Wants: Shift S1

This creates a valid cycle:

A → B → C → A

When a valid cycle is detected, the swap engine executes all swaps in the cycle.

---

# Swap Detection Logic

Each swap request represents a relationship:

User offers shift X and wants shift Y

This can be modeled as a directed graph:

X → Y

The swap engine must:

1. Load all pending swap requests
2. Build a directed graph of requests
3. Detect cycles in the graph
4. Validate operational constraints
5. Execute valid swaps
6. Update database records

---

# Operational Constraints

Before executing any swap, the engine must verify that the resulting schedules remain valid.

## Shift Ownership

A controller must own the shift they offer.

The system must verify that the shift currently belongs to that controller.

---

## No Multiple Shifts Per Day

A controller cannot receive more than one shift on the same day.

Example (invalid):

Controller receives both:

12 March Morning
12 March Evening

---

## Shift Sequence Restrictions

Certain shift sequences are not allowed due to operational safety constraints.

Examples include:

T → N
Mt → N

The engine must verify that the resulting schedule does not create illegal shift transitions.

---

## Maximum Consecutive Working Days

Controllers cannot exceed the maximum number of consecutive working days.

Maximum allowed:

9 consecutive working days

If a swap would cause a controller to exceed this limit, the swap must be rejected.

---

## Single Use of Shifts

A shift can only participate in one swap cycle.

The same shift cannot be assigned to multiple users during the same swap execution.

---

## Atomic Execution

All swaps in a cycle must be executed atomically.

This means:

• Either the entire cycle is executed
• Or none of the swaps are executed

Partial swaps are not allowed.

---

# Swap Validation Process

The swap engine should follow this validation process:

1. Detect potential swap cycle
2. Simulate the swap
3. Validate all constraints
4. If valid → execute swap
5. If invalid → reject cycle

---

# Expected Behaviour

The swap engine must prioritize:

• Safety
• Schedule validity
• Fairness between controllers

The engine must never produce an illegal schedule.

If no valid swap is possible, the system must leave schedules unchanged.
