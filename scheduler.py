"""
Two schedulers:
  1. ThreadedScheduler – uses threading.Thread to run each core.
  2. MultiprocessScheduler – uses multiprocessing.Process
     for true parallel execution (bypasses the GIL).
"""

import threading
import multiprocessing
import json

with open("config.json") as f:
    CFG = json.load(f)

NUM_CORES = CFG["num_cores"]
MAX_CYCLES = CFG["max_cycles"]


class ThreadedScheduler:
    """Each core runs in its own thread."""

    def __init__(self, cores):
        self.cores = cores

    def _core_worker(self, core):
        cap = MAX_CYCLES
        n = 0
        while not core.halted and n < cap:
            core.step()
            n += 1

    def run(self):
        threads = []
        for core in self.cores:
            t = threading.Thread(
                target=self._core_worker,
                args=(core,),
                name=f"core-{core.core_id}",
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        # Critical-path cycles = slowest core's cycle count.
        return max(c.cycles for c in self.cores)


def _core_process_worker(core, result_queue):
    """Worker for multiprocessing: runs one core to completion, sends results back."""
    output = core.run_to_completion()
    result_queue.put(
        {
            "core_id": core.core_id,
            "output": output,
            "cycles": core.cycles,
            "instructions": core.instructions,
            "stalls": core.stalls,
            "flushes": core.flushes,
            "l1_hits": core.memory.l1.hits,
            "l1_misses": core.memory.l1.misses,
            "l2_hits": core.memory.l2.hits,
            "l2_misses": core.memory.l2.misses,
        }
    )


class MultiprocessScheduler:
    """Scheduler that runs each core in its own OS process."""

    def __init__(self, cores):
        self.cores = cores

    def run(self):
        queue = multiprocessing.Queue()
        processes = []
        for core in self.cores:
            p = multiprocessing.Process(
                target=_core_process_worker, args=(core, queue)
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        # Drain the queue into a dict keyed by core_id
        results = {}
        while not queue.empty():
            r = queue.get()
            results[r["core_id"]] = r
        return results
