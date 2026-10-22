"""
2-Level Cache Hierarchy (L1 private + L2 shared) with latency simulation.
Models L1 hit, L1 miss -> L2 lookup, and L2 miss -> main memory penalty.
Tracks L1 hit rate, L2 hit rate, and AMAT (Average Memory Access Time).
"""

import json

with open("config.json") as f:
    CFG = json.load(f)


class CacheLine:
    def __init__(self, line_size):
        self.valid = False
        self.tag = 0
        self.data = [0] * line_size


class BaseCache:
    def __init__(self, size, line_size, associativity, hit_time=1):
        self.size = size
        self.line_size = line_size
        self.assoc = associativity
        self.hit_time = hit_time
        self.num_sets = max(1, size // (line_size * associativity))
        self.sets = [
            [CacheLine(line_size) for _ in range(self.assoc)]
            for _ in range(self.num_sets)
        ]
        self.hits = 0
        self.misses = 0

    def _decode(self, addr):
        offset = addr % self.line_size
        set_index = (addr // self.line_size) % self.num_sets
        tag = addr // (self.line_size * self.num_sets)
        return set_index, tag, offset

    def probe(self, addr):
        set_index, tag, offset = self._decode(addr)
        target_set = self.sets[set_index]
        for line in target_set:
            if line.valid and line.tag == tag:
                return True, line, offset
        return False, None, offset

    def insert(self, addr, block_data=None):
        set_index, tag, offset = self._decode(addr)
        target_set = self.sets[set_index]
        victim = target_set[0]
        for line in target_set:
            if not line.valid:
                victim = line
                break
        victim.valid = True
        victim.tag = tag
        if block_data is not None:
            victim.data = list(block_data)
        return victim, offset

    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    @property
    def miss_rate(self):
        total = self.hits + self.misses
        return self.misses / total if total else 0.0


class MemoryHierarchy:
    """Connects a private L1 cache, a shared L2 cache, and backing main memory."""

    def __init__(self, main_memory=None, l2_cache=None, cfg=None):
        self.cfg = cfg or CFG
        self.main_memory = main_memory if main_memory is not None else {}

        self.l1_hit_time = self.cfg.get("l1_hit_time", 1)
        self.l2_hit_time = self.cfg.get("l2_hit_time", 10)
        self.mem_penalty = self.cfg.get("mem_penalty", 50)

        # Private L1 cache
        l1_size = self.cfg.get("cache_size", 1024)
        l1_line = self.cfg.get("cache_line_size", 16)
        l1_assoc = self.cfg.get("cache_associativity", 2)
        self.l1 = BaseCache(l1_size, l1_line, l1_assoc, hit_time=self.l1_hit_time)

        # Shared L2 cache
        if l2_cache is not None:
            self.l2 = l2_cache
        else:
            l2_size = self.cfg.get("l2_size", 4096)
            l2_line = self.cfg.get("l2_line_size", 16)
            l2_assoc = self.cfg.get("l2_associativity", 4)
            self.l2 = BaseCache(l2_size, l2_line, l2_assoc, hit_time=self.l2_hit_time)

    def read(self, addr):
        """Read from memory through L1 -> L2 -> Main Memory.

        Returns (value, latency).
        """
        # 1. L1 lookup
        hit1, line1, off1 = self.l1.probe(addr)
        if hit1:
            self.l1.hits += 1
            return line1.data[off1], self.l1_hit_time

        # L1 Miss -> L2 lookup
        self.l1.misses += 1
        hit2, line2, off2 = self.l2.probe(addr)
        if hit2:
            self.l2.hits += 1
            val = line2.data[off2]
            # Allocate in L1
            self.l1.insert(addr, line2.data)
            return val, self.l1_hit_time + self.l2_hit_time

        # L2 Miss -> Main Memory fetch
        self.l2.misses += 1
        val = self.main_memory.get(addr, 0)
        # Construct line block
        block = [0] * self.l1.line_size
        block[off1] = val
        self.l2.insert(addr, block)
        self.l1.insert(addr, block)
        return val, self.l1_hit_time + self.l2_hit_time + self.mem_penalty

    def write(self, addr, val):
        """Write-through to main memory and update/allocate in caches."""
        self.main_memory[addr] = val

        # Update/allocate in L1
        hit1, line1, off1 = self.l1.probe(addr)
        if hit1:
            self.l1.hits += 1
            line1.data[off1] = val
        else:
            self.l1.misses += 1
            block = [0] * self.l1.line_size
            block[off1] = val
            self.l1.insert(addr, block)

        # Update/allocate in L2
        hit2, line2, off2 = self.l2.probe(addr)
        if hit2:
            self.l2.hits += 1
            line2.data[off2] = val
        else:
            self.l2.misses += 1
            block = [0] * self.l2.line_size
            block[off2] = val
            self.l2.insert(addr, block)

    def access(self, addr):
        """Compatibility helper returning value."""
        val, _ = self.read(addr)
        return val

    @property
    def hits(self):
        return self.l1.hits

    @property
    def misses(self):
        return self.l1.misses

    @property
    def hit_rate(self):
        return self.l1.hit_rate

    @property
    def amat(self):
        """AMAT = L1_hit_time + L1_miss_rate * (L2_hit_time + L2_miss_rate * mem_penalty)"""
        l1_miss_rate = self.l1.miss_rate
        l2_miss_rate = self.l2.miss_rate
        return self.l1_hit_time + l1_miss_rate * (
            self.l2_hit_time + l2_miss_rate * self.mem_penalty
        )


# Legacy Cache alias for backward compatibility
Cache = MemoryHierarchy