"""
Collect and report performance metrics for the multi-core CPU simulator.
Calculates Aggregate CPI, Per-Core CPI, L1 Hit Rate, L2 Hit Rate,
and Average Memory Access Time (AMAT).
"""

import json

with open("config.json") as f:
    CFG = json.load(f)


def gather_metrics(cores, cache, cycles):
    """Return a dictionary of aggregate metrics across all cores and cache levels."""
    total_instr = sum(c.instructions for c in cores)
    total_cycles = sum(c.cycles for c in cores)
    aggregate_cpi = total_cycles / total_instr if total_instr else 0.0

    total_stalls = sum(c.stalls for c in cores)
    total_flushes = sum(c.flushes for c in cores)

    # L1 cache stats aggregated across private L1s
    l1_hits = sum(c.memory.l1.hits for c in cores)
    l1_misses = sum(c.memory.l1.misses for c in cores)
    # If cache has hits/misses assigned directly (e.g. from scheduler aggregation)
    if hasattr(cache, "hits") and cache.hits > 0 and l1_hits == 0:
        l1_hits = cache.hits
        l1_misses = cache.misses

    l1_total = l1_hits + l1_misses
    l1_hit_rate = l1_hits / l1_total if l1_total else 0.0
    l1_miss_rate = l1_misses / l1_total if l1_total else 0.0

    # L2 cache stats from shared L2
    l2_hits = cache.l2.hits if hasattr(cache, "l2") else getattr(cache, "l2_hits", 0)
    l2_misses = (
        cache.l2.misses if hasattr(cache, "l2") else getattr(cache, "l2_misses", 0)
    )
    l2_total = l2_hits + l2_misses
    l2_hit_rate = l2_hits / l2_total if l2_total else 0.0
    l2_miss_rate = l2_misses / l2_total if l2_total else 0.0

    l1_hit_time = getattr(cache, "l1_hit_time", CFG.get("l1_hit_time", 1))
    l2_hit_time = getattr(cache, "l2_hit_time", CFG.get("l2_hit_time", 10))
    mem_penalty = getattr(cache, "mem_penalty", CFG.get("mem_penalty", 50))

    # AMAT = L1_hit_time + L1_miss_rate * (L2_hit_time + L2_miss_rate * mem_penalty)
    amat = l1_hit_time + l1_miss_rate * (
        l2_hit_time + l2_miss_rate * mem_penalty
    )

    metrics = {
        "total_cycles": cycles,
        "sum_core_cycles": total_cycles,
        "total_instructions": total_instr,
        "aggregate_cpi": round(aggregate_cpi, 4),
        "total_stalls": total_stalls,
        "total_flushes": total_flushes,
        "l1_hits": l1_hits,
        "l1_misses": l1_misses,
        "l1_hit_rate": round(l1_hit_rate, 4),
        "l2_hits": l2_hits,
        "l2_misses": l2_misses,
        "l2_hit_rate": round(l2_hit_rate, 4),
        "amat": round(amat, 4),
        "per_core": [],
    }

    for c in cores:
        metrics["per_core"].append(
            {
                "core_id": c.core_id,
                "cycles": c.cycles,
                "instructions": c.instructions,
                "cpi": round(c.cycles / c.instructions, 4) if c.instructions else 0.0,
                "stalls": c.stalls,
                "flushes": c.flushes,
            }
        )

    # Sorted by instructions descending (busiest cores first)
    metrics["per_core"] = sorted(
        metrics["per_core"], key=lambda x: x["instructions"], reverse=True
    )

    return metrics


def print_report(metrics):
    print("=" * 65)
    print("  HIGH-PERFORMANCE CPU SIMULATOR – ARCHITECTURE REPORT")
    print("=" * 65)
    print(f"  Critical-path cycles  : {metrics['total_cycles']}")
    print(f"  Total instructions    : {metrics['total_instructions']}")
    print(f"  Aggregate CPI         : {metrics['aggregate_cpi']:.4f}")
    print(f"  Pipeline Stalls       : {metrics['total_stalls']}")
    print(f"  Branch Flushes        : {metrics['total_flushes']}")
    print("-" * 65)
    print("  2-LEVEL CACHE HIERARCHY & AMAT METRICS:")
    print(
        f"  L1 Cache (Private)    : Hits={metrics['l1_hits']}, Misses={metrics['l1_misses']}, Hit Rate={metrics['l1_hit_rate'] * 100:.2f}%"
    )
    print(
        f"  L2 Cache (Shared)     : Hits={metrics['l2_hits']}, Misses={metrics['l2_misses']}, Hit Rate={metrics['l2_hit_rate'] * 100:.2f}%"
    )
    print(f"  AMAT                  : {metrics['amat']:.4f} cycles")
    print("-" * 65)
    print("  Per-core breakdown (sorted by instructions):")
    for pc in metrics["per_core"]:
        print(
            f"    Core {pc['core_id']:2d} | "
            f"cycles={pc['cycles']:5d} | "
            f"instr={pc['instructions']:5d} | "
            f"CPI={pc['cpi']:.4f} | "
            f"stalls={pc['stalls']:2d} | "
            f"flushes={pc['flushes']:2d}"
        )
    print("=" * 65)
