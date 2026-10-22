# pipelined-cpu-sim

A from-scratch, **10-core 64-bit pipelined CPU simulator** written in pure Python.  
Models a real micro-architecture end-to-end: a custom ISA, a 2-pass assembler, a 5-stage pipeline with data-hazard forwarding and branch penalties, a 2-level private/shared cache hierarchy, and a parallel scheduler — all driven by benchmark programs that exercise every feature.

---

## Table of Contents

- [Motivation](#motivation)
- [Feature Highlights](#feature-highlights)
- [Architecture Overview](#architecture-overview)
  - [System Layout](#system-layout)
  - [ISA Reference](#isa-reference)
  - [Instruction Encoding (32-bit)](#instruction-encoding-32-bit)
  - [5-Stage Pipeline](#5-stage-pipeline)
  - [Cache Hierarchy](#cache-hierarchy)
  - [Scheduler Modes](#scheduler-modes)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Requirements](#requirements)
  - [Run](#run)
  - [Run Tests](#run-tests)
  - [Configuration](#configuration)
- [Sample Output](#sample-output)
- [Benchmarks](#benchmarks)
- [Performance Metrics Explained](#performance-metrics-explained)
- [Roadmap](#roadmap)

---

## Motivation

Most CPU simulators are either toy projects (single instruction, no memory model) or heavyweight RTL simulators. This project sits deliberately in the middle — complex enough to produce meaningful micro-architectural numbers (variable CPI, AMAT, stall rates) while remaining readable Python you can step through with a debugger.

It was built incrementally:

| Phase | What was added |
|---|---|
| Phase 0 | 10-core scheduler skeleton, threaded & multiprocess modes |
| Phase 1 | Full ISA (memory, stack, flags, branches), 2-pass assembler, 32-bit encoding |
| Phase 2 | 5-stage pipeline with forwarding + stalls, 2-level cache hierarchy, AMAT reporting |

---

## Feature Highlights

- **31-opcode custom ISA** — ALU, memory load/store (register-indirect and absolute), stack (PUSH/POP), subroutines (CALL/RET), condition flags (ZF/SF) and conditional branches (JE/JNE/JL/JGE)
- **32-bit packed instruction encoding** — 3 formats (R-type, I-type, J-type) decoded with bitmasks, matching real RISC design
- **5-stage pipeline** — Instruction Fetch → Decode → Execute → Memory → Write-Back, clocked with explicit pipeline registers
- **Forwarding unit** — EX/MEM → EX and MEM/WB → EX bypasses eliminate most RAW stalls
- **Load-use hazard detection** — inserts a 1-cycle bubble when a load result is needed in the very next ALU instruction
- **Branch penalty** — taken branches (JMP, JNZ, CALL, RET, JE, JNE, JL, JGE) flush IF and ID stages, simulating a 2-cycle branch penalty
- **2-level cache hierarchy** — private L1 (1 KB, 2-way) per core + shared L2 (4 KB, 4-way) + dict-backed main memory, with configurable hit times and miss penalty
- **AMAT calculation** — `L1_hit_time + L1_miss_rate × (L2_hit_time + L2_miss_rate × mem_penalty)`
- **Dual scheduler** — `--mode threaded` (Python threads, shared memory) or `--mode multiprocess` (OS processes, true parallelism, stats aggregated via Queue)
- **Regression test suite** — 7 tests covering ALU correctness, load-use stalls, forwarding, branch semantics, and realistic CPI bounds

---

## Architecture Overview

### System Layout

```
main.py  ──▶  build_demo_cores()
                  │
                  ├── Assembler (assembler.py)   2-pass → List[int32]
                  ├── demo_programs.py            3 benchmarks
                  └── 10 × Core (cpu_core.py)    each with private L1
                            │
                     ┌──────▼──────┐
                     │  Scheduler  │   threaded / multiprocess
                     └──────┬──────┘
                            │
                     ┌──────▼──────────────────────┐
                     │  5-Stage Pipeline (per core) │
                     │  IF → ID → EX → MEM → WB    │
                     │  + Forwarding + Stall logic  │
                     └──────┬──────────────────────┘
                            │
                     ┌──────▼──────────────────────┐
                     │  Memory Hierarchy (cache.py) │
                     │  L1 (private) → L2 (shared)  │
                     │             → Main Memory    │
                     └─────────────────────────────┘
                            │
                     performance.py  →  Architecture Report
```

### ISA Reference

| Category | Mnemonics |
|---|---|
| **Load immediate / Move** | `LOAD Rd, imm` · `MOV Rd, Rs` |
| **ALU (register)** | `ADD` · `SUB` · `MUL` · `DIV` · `AND` · `OR` · `XOR` |
| **ALU (immediate)** | `ADDI Rd, Rs, imm` · `SHL Rd, Rs, imm` · `SHR Rd, Rs, imm` |
| **Memory (register-indirect)** | `LD Rd, Rs` — `Rd = mem[Rs]` · `ST Rd, Rs` — `mem[Rd] = Rs` |
| **Memory (absolute address)** | `LDI Rd, addr` — `Rd = mem[addr]` · `STI addr, Rs` — `mem[addr] = Rs` |
| **Stack** | `PUSH Rs` · `POP Rd` |
| **Subroutines** | `CALL target` — push PC+1; jump · `RET` — pop; jump |
| **Compare** | `CMP Rs1, Rs2` · `CMPI Rs1, imm` — sets ZF and SF |
| **Conditional branch** | `JE` · `JNE` · `JL` · `JGE` — all take a label target |
| **Unconditional branch** | `JMP target` · `JNZ Rs, target` |
| **System** | `PRINT Rs` · `NOP` · `HALT` |

- **Registers**: `R0`–`R30` (64-bit GPRs) + `SP` alias for `R31`
- **Stack pointer**: `SP = R31`, initialised per core to `4096 + core_id × 512` (no overlap between cores)
- **Condition flags**: `ZF` (zero / equal) and `SF` (sign / less-than), set by `CMP`/`CMPI`

### Instruction Encoding (32-bit)

```
R-type   [31:26 opcode] [25:21 rd] [20:16 rs1] [15:11 rs2] [10:0 unused]
I-type   [31:26 opcode] [25:21 rd] [20:16 rs1] [15:0  imm16 (sign-extended)]
J-type   [31:26 opcode] [20:0  target21]
JNZ      [31:26 opcode] [20:16 rs1] [15:0 target16]
```

Encoding is handled by `pack_instruction()` in [`assembler.py`](assembler.py); decoding at runtime by `decode_instruction()` using bitwise masks.

### 5-Stage Pipeline

```
IF ──▶ IF/ID ──▶ ID ──▶ ID/EX ──▶ EX ──▶ EX/MEM ──▶ MEM ──▶ MEM/WB ──▶ WB
```

Each stage reads its input pipeline register and writes the *next* pipeline register; all four registers are committed simultaneously at the end of `Core.step()`.

| Hazard | Detection point | Mitigation |
|---|---|---|
| **Load-use RAW** | ID stage checks `id_ex.is_mem_read` and `id_ex.rd ∈ {rs1, rs2}` | 1-cycle bubble inserted; IF/ID frozen |
| **ALU RAW** | EX forwarding unit checks EX/MEM and MEM/WB | Value bypassed into EX inputs; no stall |
| **Control (branch)** | EX stage resolves taken/not-taken | IF and ID flushed (2-cycle penalty) |

### Cache Hierarchy

| Level | Size | Associativity | Line size | Hit time | Scope |
|---|---|---|---|---|---|
| **L1** | 1 KB | 2-way set-associative | 16 B | 1 cycle | Private per core |
| **L2** | 4 KB | 4-way set-associative | 16 B | 10 cycles | Shared across all cores |
| **Main memory** | 64 KB (dict) | — | — | 50-cycle penalty | Global |

**AMAT formula:**
```
AMAT = L1_hit_time + L1_miss_rate × (L2_hit_time + L2_miss_rate × mem_penalty)
```

Write policy: **write-through** — stores always update `main_memory` and invalidate/update any matching L1/L2 line.

### Scheduler Modes

| Mode | Mechanism | Notes |
|---|---|---|
| `threaded` | `threading.Thread` per core | Shared memory; L2 and main memory truly shared; GIL-bound |
| `multiprocess` | `multiprocessing.Process` per core | Isolated address spaces; L1/L2 stats serialised back to parent via `Queue` |

---

## Project Structure

```
pipelined-cpu-sim/
├── config.json          # Hardware parameters (cores, cache sizes, latencies)
├── assembler.py         # 2-pass assembler + 32-bit pack/decode helpers
├── cache.py             # BaseCache, MemoryHierarchy (L1 private + L2 shared)
├── cpu_core.py          # Core: 5-stage pipeline, forwarding, hazards, flags
├── demo_programs.py     # Benchmarks: recursive Fibonacci, bubble sort, string reverse
├── scheduler.py         # ThreadedScheduler, MultiprocessScheduler
├── performance.py       # gather_metrics(), print_report() — CPI, AMAT, per-core
├── main.py              # CLI entry point: build cores, run, report
└── test_suite.py        # 7 regression tests (ALU, memory, stack, branches, pipeline)
```

---

## Getting Started

### Requirements

- **Python 3.10+** (uses `match`-style structural patterns internally; no third-party packages required)

```bash
python3 --version
```

### Run

```bash
cd pipelined-cpu-sim

# Default: threaded scheduler
python3 main.py

# Explicit threaded
python3 main.py --mode threaded

# Multiprocess (true OS-level parallelism)
python3 main.py --mode multiprocess
```

### Run Tests

```bash
python3 test_suite.py
```

Expected output:
```
✓ basic ALU
✓ memory LD/ST (stalls=1)
✓ stack + subroutines
✓ flags + signed branch JL
✓ ALU forwarding (stalls=0)
✓ load-use stall (stalls=1)
✓ realistic CPI (1.452 over 209 instrs)

7/7 tests passed
```

### Configuration

All hardware parameters live in [`config.json`](config.json):

```json
{
  "num_cores":          10,
  "register_bits":      64,
  "num_registers":      32,
  "cache_size":         1024,
  "cache_line_size":    16,
  "cache_associativity": 2,
  "l1_hit_time":        1,
  "l2_size":            4096,
  "l2_line_size":       16,
  "l2_associativity":   4,
  "l2_hit_time":        10,
  "mem_penalty":        50,
  "memory_size":        65536,
  "pipeline_stages":    5,
  "max_cycles":         50000,
  "scheduler_mode":     "threaded"
}
```

Change `scheduler_mode` here to set the default without passing `--mode`.

---

## Sample Output

```
>>> Starting 10-core 64-bit CPU simulator (mode=threaded) <<<

Core  0 output: [5]
Core  1 output: [17, 42, 56, 89]
Core  2 output: [37, 85, 80, 33]
Core  3 output: [5]
Core  4 output: [57, 31, 93, 24]
Core  5 output: [37, 85, 80, 33]
Core  6 output: [5]
Core  7 output: [71, 20, 44, 68]
Core  8 output: [85, 37, 33, 80]
Core  9 output: [5]

=================================================================
  HIGH-PERFORMANCE CPU SIMULATOR – ARCHITECTURE REPORT
=================================================================
  Critical-path cycles  : 3241
  Total instructions    : 2093
  Aggregate CPI         : 1.5474
  Pipeline Stalls       : 103
  Branch Flushes        : 174
-----------------------------------------------------------------
  2-LEVEL CACHE HIERARCHY & AMAT METRICS:
  L1 Cache (Private)    : Hits=1847, Misses=163, Hit Rate=91.86%
  L2 Cache (Shared)     : Hits=135,  Misses=28,  Hit Rate=82.82%
  AMAT                  : 2.5016 cycles
-----------------------------------------------------------------
  Per-core breakdown (sorted by instructions):
    Core  1 | cycles= 678 | instr= 347 | CPI=1.9539 | stalls=18 | flushes=27
    Core  4 | cycles= 621 | instr= 313 | CPI=1.9840 | stalls=16 | flushes=24
    ...
    Core  0 | cycles= 158 | instr= 117 | CPI=1.3504 | stalls= 8 | flushes=34
=================================================================
```

---

## Benchmarks

Three benchmark programs are assembled and distributed across the 10 cores by `core_id % 3`:

### Recursive Fibonacci (`core_id % 3 == 0`)
Computes `fib(n)` recursively using the call stack. Exercises `CALL`, `RET`, `PUSH`, `POP`, `CMPI`, `JL`, `JE`, and `ADD`. Produces high branch-flush rates.

### In-memory Bubble Sort (`core_id % 3 == 1`)
Sorts 4 elements in main memory over 3 passes using `LDI`/`STI`, `CMP`, `JL`, and `JNZ`. Produces load-use stalls and realistic cache traffic.

### Stack-based String Reverse (`core_id % 3 == 2`)
Stores 4 ASCII values to memory, pushes them onto the stack in order, pops them in reverse, and writes them back. Exercises `PUSH`/`POP`, `LDI`/`STI`, and forwarding paths.

---

## Performance Metrics Explained

| Metric | Definition |
|---|---|
| **Critical-path cycles** | `max(core.cycles)` — the wall-clock cycle count (slowest core) |
| **Aggregate CPI** | `Σ(core.cycles) / Σ(core.instructions)` across all cores |
| **Pipeline stalls** | Load-use bubbles inserted (1 cycle each) |
| **Branch flushes** | Taken-branch flush events (2 pipeline stages cleared each time) |
| **L1 hit rate** | `l1_hits / (l1_hits + l1_misses)` aggregated across all private L1s |
| **L2 hit rate** | `l2_hits / (l2_hits + l2_misses)` on the shared L2 |
| **AMAT** | `t_L1 + m_L1 × (t_L2 + m_L2 × t_mem)` in cycles |

---

## Roadmap

### ✅ Pipeline & ISA
- [ ] Branch predictor (2-bit saturating counter) to reduce flush rate
- [ ] Out-of-order execution skeleton (reorder buffer + reservation stations)
- [ ] ELF-like binary loader so external programs can be run without recompiling
- [ ] Web-based pipeline visualiser (step-through mode)

### 🧠 Cache & Memory Hierarchies
- [ ] **L3 cache layer** — Add a shared L3 (e.g. 16 KB, 8-way) between the shared L2 and main memory; extend AMAT formula to a 3-level model (`t_L1 + m_L1×(t_L2 + m_L2×(t_L3 + m_L3×t_mem))`) and benchmark how L3 size/associativity affects hit rates and CPI across workloads
- [ ] **Cache hierarchy design explorer** — Sweep L1/L2/L3 size configurations programmatically and plot the Pareto frontier of AMAT vs. silicon area cost, reproducing the kind of design-space analysis done in real CPU architecture teams
- [ ] Cache coherence protocol (MESI) for the shared L2/L3 in multicore mode

### ⚡ GPU & Systolic Architecture
- [ ] **Systolic array matrix multiplier** — Model an N×N systolic array (as used in Google TPUs and NVIDIA tensor cores) where each PE does a MAC every cycle; data flows in a wave across the array with no global interconnect; simulate the dataflow schedule (weight-stationary vs. output-stationary) and report utilisation and effective FLOP/s
- [ ] **GPU architecture simulator** — Extend the multi-core model into a SIMT (Single Instruction Multiple Threads) GPU: warp scheduler, warp-level divergence handling, shared memory scratchpad per SM, and a global memory coalescing model; compare throughput vs. the CPU pipeline on the matrix multiply benchmark

### 🤖 RL-Driven Cache Scheduler
- [ ] **Reinforcement Learning cache arbitration agent** — Replace the fixed round-robin L2 access order with a tabular Q-learning agent (pure Python, no ML libraries):
  - **State**: per-core stall count, L1 miss rate, and pipeline occupancy sampled each scheduling quantum
  - **Action**: which core gets L2 priority this quantum (discrete, one-hot over 10 cores)
  - **Reward**: negative of total pipeline stalls incurred during the quantum (fewer stalls = higher reward)
  - **Learning**: ε-greedy exploration decaying over training episodes; Q-table updated with `Q(s,a) ← Q(s,a) + α(r + γ·max Q(s',·) − Q(s,a))`
  - **Deliverable**: side-by-side graph — Round-Robin vs. RL agent — plotting total cycles to completion on skewed workloads (one memory-heavy core + nine compute-heavy cores); expect the RL agent to converge on a policy that drains the bottlenecked core's miss queue first, reducing overall wall-clock cycles
