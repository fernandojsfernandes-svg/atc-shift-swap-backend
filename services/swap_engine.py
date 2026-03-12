"""
Detects swap cycles from OPEN swap requests.
Supports same-day cycles (legacy) and cross-day cycles via wanted_options.
"""
from sqlalchemy.orm import Session


def _wanted_set_for_swap(swap, shift, db: Session, swap_wanted_option_model, shift_type_model):
    """
    Returns set of (date, shift_type_id) that this swap "wants".
    If the swap has wanted_options, use those; else same-day, any other type (legacy).
    """
    wanted = set()
    opts = db.query(swap_wanted_option_model).filter(
        swap_wanted_option_model.swap_request_id == swap.id
    ).all()
    if opts:
        for o in opts:
            wanted.add((o.date, o.shift_type_id))
        return wanted
    # Legacy: same day, any shift type different from offered shift
    if not shift or shift.shift_type_id is None:
        return wanted
    all_types = db.query(shift_type_model).all()
    for st in all_types:
        if st.id != shift.shift_type_id:
            wanted.add((shift.data, st.id))
    return wanted


def _build_graph(swaps, db: Session, swap_wanted_option_model, shift_type_model):
    """
    Build directed graph: edge swap_i -> swap_j if swap_i wants the shift offered by swap_j.
    Returns: list of (swap_id, list of successor swap_ids).
    """
    # shift_id -> (date, shift_type_id) for offered shifts
    shift_info = {}
    for s in swaps:
        sh = s.shift
        if not sh:
            continue
        shift_info[s.id] = (sh.data, sh.shift_type_id if sh.shift_type_id is not None else None)
    # For shifts without shift_type_id we can't match by type; skip those edges
    wanted_by_swap = {}
    for s in swaps:
        sh = s.shift
        if not sh:
            continue
        wanted_by_swap[s.id] = _wanted_set_for_swap(s, sh, db, swap_wanted_option_model, shift_type_model)
    # adjacency: swap_id -> [swap_id]
    graph = {s.id: [] for s in swaps}
    for si in swaps:
        if si.id not in wanted_by_swap:
            continue
        want = wanted_by_swap[si.id]
        for sj in swaps:
            if si.id == sj.id:
                continue
            info = shift_info.get(sj.id)
            if not info:
                continue
            date_j, type_j = info
            if type_j is None:
                continue
            if (date_j, type_j) in want:
                graph[si.id].append(sj.id)
    return graph


def _find_cycles_from(graph, start, max_cycle_len=6):
    """DFS from start; return list of cycles (each cycle = list of swap ids)."""
    cycles = []
    path = []
    path_set = set()
    path_index = {}

    def dfs(node):
        path.append(node)
        path_set.add(node)
        path_index[node] = len(path) - 1
        for succ in graph.get(node, []):
            if succ in path_set:
                # cycle: from path_index[succ] to end (succ closes the loop)
                cy = path[path_index[succ]:]
                if 2 <= len(cy) <= max_cycle_len:
                    cycles.append(cy[:])
            elif len(path) < max_cycle_len:
                dfs(succ)
        path.pop()
        path_set.discard(node)
        del path_index[node]

    dfs(start)
    return cycles


def _normalize_cycle(cycle):
    """Rotate so smallest id is first, then return tuple."""
    if not cycle:
        return ()
    i = min(range(len(cycle)), key=lambda i: cycle[i])
    return tuple(cycle[i:] + cycle[:i])


def detect_swap_cycles(swaps, db: Session = None, swap_wanted_option_model=None, shift_type_model=None):
    """
    Detects cycles in OPEN swap requests.
    If db and models are provided, uses wanted_options (and same-day fallback).
    Otherwise falls back to legacy same-day 3-way only.
    """
    if not swaps:
        return []

    # Lazy imports to avoid circular imports
    if swap_wanted_option_model is None and db is not None:
        from models import SwapWantedOption, ShiftType
        swap_wanted_option_model = SwapWantedOption
        shift_type_model = ShiftType

    if db is not None and swap_wanted_option_model is not None and shift_type_model is not None:
        graph = _build_graph(swaps, db, swap_wanted_option_model, shift_type_model)
        all_cycles = []
        seen = set()
        for s in swaps:
            for cy in _find_cycles_from(graph, s.id):
                key = _normalize_cycle(cy)
                if key not in seen:
                    seen.add(key)
                    all_cycles.append({
                        "cycle": list(key),
                        "message": f"{len(key)}-way swap possible",
                    })
        return all_cycles

    # Legacy: same-day 3-way only
    cycles = []
    seen_cycles = set()
    for swap_a in swaps:
        shift_a = swap_a.shift
        if not shift_a:
            continue
        for swap_b in swaps:
            if swap_b.id == swap_a.id:
                continue
            shift_b = swap_b.shift
            if not shift_b:
                continue
            if shift_a.data != shift_b.data:
                continue
            if shift_a.codigo == shift_b.codigo:
                continue
            for swap_c in swaps:
                if swap_c.id in [swap_a.id, swap_b.id]:
                    continue
                shift_c = swap_c.shift
                if not shift_c:
                    continue
                if shift_b.data != shift_c.data:
                    continue
                if shift_c.codigo == shift_a.codigo:
                    continue
                if shift_c.data != shift_a.data:
                    continue
                cycle = [swap_a.id, swap_b.id, swap_c.id]
                cycle_key = tuple(sorted(cycle))
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    cycles.append({
                        "cycle": cycle,
                        "date": str(shift_a.data),
                        "message": "3-way swap possible"
                    })
    return cycles
