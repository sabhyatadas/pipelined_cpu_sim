"""
Main entry point for the 10-core 64-bit HPC Architecture Simulator.
Runs a 5-stage pipelined processor with forwarding, 2-level cache hierarchy,
and workloads (recursive Fibonacci, bubble sort, string reverse).

Usage:
    python3 main.py                    # runs the default demo (threaded)
    python3 main.py --mode threaded    # threaded scheduler
    python3 main.py --mode multiprocess
"""

import argparse
import json

from cpu_core import Core
from cache import MemoryHierarchy, BaseCache
from scheduler import ThreadedScheduler, MultiprocessScheduler
from demo_programs import (
    program_recursive_fibonacci,
    program_bubble_sort,
    program_string_reverse,
)
from performance import gather_metrics, print_report

with open("config.json") as f:
    CFG = json.load(f)

NUM_CORES = CFG["num_cores"]


def build_demo_cores():
    """Create 10 cores with a mix of recursive Fibonacci, bubble sort, and string reverse."""
    programs = []
    for i in range(NUM_CORES):
        if i % 3 == 0:
            programs.append(program_recursive_fibonacci(n=5 + (i % 3)))
        elif i % 3 == 1:
            programs.append(program_bubble_sort(seed=i))
        else:
            programs.append(program_string_reverse(seed=i))

    shared_memory = {}
    shared_l2 = BaseCache(
        size=CFG.get("l2_size", 4096),
        line_size=CFG.get("l2_line_size", 16),
        associativity=CFG.get("l2_associativity", 4),
        hit_time=CFG.get("l2_hit_time", 10),
    )

    cores = []
    for i in range(NUM_CORES):
        # Each core receives private L1 cache, while sharing L2 and main memory
        mem_hier = MemoryHierarchy(
            main_memory=shared_memory,
            l2_cache=shared_l2,
            cfg=CFG,
        )
        cores.append(Core(i, programs[i], mem_hier))

    sys_cache = MemoryHierarchy(
        main_memory=shared_memory, l2_cache=shared_l2, cfg=CFG
    )
    return cores, sys_cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["threaded", "multiprocess"],
        default=CFG.get("scheduler_mode", "threaded"),
    )
    args = parser.parse_args()

    print(
        f"\n>>> Starting 10-core 64-bit CPU simulator (mode={args.mode}) <<<\n"
    )

    cores, cache = build_demo_cores()

    if args.mode == "threaded":
        sched = ThreadedScheduler(cores)
        cycles = sched.run()
        for core in cores:
            print(f"Core {core.core_id:2d} output: {core.output}")
    else:
        sched = MultiprocessScheduler(cores)
        results = sched.run()

        # Update parent Core objects from multiprocess worker results
        for core in cores:
            r = results.get(core.core_id)
            if r is not None:
                core.output = r["output"]
                core.cycles = r["cycles"]
                core.instructions = r["instructions"]
                core.stalls = r.get("stalls", 0)
                core.flushes = r.get("flushes", 0)
                core.memory.l1.hits = r.get("l1_hits", 0)
                core.memory.l1.misses = r.get("l1_misses", 0)
                core.halted = True
                print(f"Core {core.core_id:2d} output: {core.output}")

        # In multiprocess mode, critical path cycles equals slowest core's cycle count
        cycles = max((c.cycles for c in cores), default=0)

        # Sum cache hits and misses reported by child processes into system cache
        cache.l1.hits = sum(r.get("l1_hits", 0) for r in results.values())
        cache.l1.misses = sum(r.get("l1_misses", 0) for r in results.values())
        cache.l2.hits = sum(r.get("l2_hits", 0) for r in results.values())
        cache.l2.misses = sum(r.get("l2_misses", 0) for r in results.values())

    metrics = gather_metrics(cores, cache, cycles)
    print_report(metrics)


if __name__ == "__main__":
    main()
