def detect_swap_cycles(swaps):

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