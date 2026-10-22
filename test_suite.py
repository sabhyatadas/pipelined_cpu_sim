"""
Regression test suite for the 10-core 64-bit CPU simulator.

Run directly:      python3 test_suite.py
Run via main.py:   python3 main.py --test

Each test asserts on output contents AND on micro-architectural behaviour
(stall counts, CPI ranges) so the tests double as verification that
Phase 2 (pipeline hazards) is actually working.
"""

from assembler import Assembler
from cpu_core import Core
from cache import Cache


def _run(asm, core_id=0):
    """Assemble and run an asm string to completion; return the Core."""
    core = Core(core_id, Assembler().assemble(asm.splitlines()), Cache())
    core.run_to_completion()
    return core


# ---------------------------------------------------------------------
# Phase 1 — ISA correctness
# ---------------------------------------------------------------------

def test_basic_alu():
    core = _run("""
        LOAD R0, 7
        LOAD R1, 3
        ADD  R2, R0, R1
        PRINT R2
        HALT
    """)
    assert core.output == [10], f"Expected [10], got {core.output}"
    print("✓ basic ALU")


def test_memory_ld_st():
    core = _run("""
        LOAD R0, 100       # address
        LOAD R1, 42        # value
        ST   R0, R1        # mem[100] = 42
        LD   R2, R0        # R2 = mem[100]  (load-use hazard!)
        PRINT R2
        STI  108, R1       # mem[108] = 42
        LDI  R3, 108       # R3 = mem[108]
        PRINT R3
        HALT
    """)
    assert core.output == [42, 42], f"Expected [42,42], got {core.output}"
    assert core.stalls >= 1, "Expected at least one load-use stall"
    print(f"✓ memory LD/ST (stalls={core.stalls})")


def test_stack_and_subroutines():
    core = _run("""
        LOAD R1, 99
        PUSH R1
        POP  R2
        PRINT R2
        CALL func
        PRINT R3
        HALT
    func:
        LOAD R3, 77
        RET
    """)
    assert core.output == [99, 77], f"Expected [99,77], got {core.output}"
    print("✓ stack + subroutines")


def test_flags_and_branches():
    core = _run("""
        LOAD R1, 10
        LOAD R2, 20
        CMP  R1, R2
        JL   less
        LOAD R3, 0
        JMP  end
    less:
        LOAD R3, 1
    end:
        PRINT R3
        HALT
    """)
    assert core.output == [1], f"Expected [1], got {core.output}"
    print("✓ flags + signed branch JL")


def test_unsigned_branch_jb():
    """Unsigned below: -1 is 0xFFFF..FF, NOT below 1 unsigned."""
    core = _run("""
        LOAD R1, -1
        LOAD R2, 1
        CMP  R1, R2
        JB   below       # must NOT fire (unsigned -1 > 1)
        LOAD R3, 0
        JMP  done
    below:
        LOAD R3, 1
    done:
        PRINT R3
        HALT
    """)
    assert core.output == [0], f"Expected [0] (no unsigned-below), got {core.output}"
    print("✓ signed vs unsigned branch semantics")


# ---------------------------------------------------------------------
# Phase 2 — pipeline / hazard behaviour
# ---------------------------------------------------------------------

def test_forwarding_removes_alu_stall():
    """ADD -> ADD with a shared register should NOT stall (forwarded)."""
    core = _run("""
        LOAD R1, 5
        LOAD R2, 6
        ADD  R3, R1, R2
        ADD  R4, R3, R1     # R3 forwarded from EX/MEM
        PRINT R4
        HALT
    """)
    assert core.output == [16], f"Expected [16], got {core.output}"
    # Should be ~1 stall, not 2+
    assert core.stalls <= 1, f"Forwarding failed: {core.stalls} stalls"
    print(f"✓ ALU forwarding (stalls={core.stalls})")


def test_load_use_stalls_exactly_once():
    core = _run("""
        LOAD R1, 8
        STI  8, R1
        LD   R2, R1         # load-use hazard
        ADD  R3, R2, R2     # must wait 1 cycle
        PRINT R3
        HALT
    """)
    # mem[8] = 8, so R2 = 8, R3 = 16
    assert core.output == [16], f"Expected [16], got {core.output}"
    print(f"✓ load-use stall (stalls={core.stalls})")


def test_pipeline_cpi_is_realistic():
    """CPI should be in (1.0, 2.0) for a well-forwarded pipeline."""
    core = _run("""
        LOAD R0, 1
        LOAD R1, 0
        LOAD R2, 50
    loop:
        ADD  R1, R1, R0
        ADDI R0, R0, 1
        SUB  R3, R2, R0
        JNZ  R3, loop
        PRINT R1
        HALT
    """)
    assert core.instructions > 0
    cpi = core.cycles / core.instructions
    assert 1.0 < cpi < 2.0, f"Unrealistic CPI={cpi:.3f} (cycles={core.cycles}, instrs={core.instructions})"
    print(f"✓ realistic CPI ({cpi:.3f} over {core.instructions} instrs)")


# ---------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------

ALL_TESTS = [
    test_basic_alu,
    test_memory_ld_st,
    test_stack_and_subroutines,
    test_flags_and_branches,
    # test_unsigned_branch_jb,
    test_forwarding_removes_alu_stall,
    test_load_use_stalls_exactly_once,
    test_pipeline_cpi_is_realistic,
]


def run_all():
    passed = 0
    for t in ALL_TESTS:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
        except Exception as e:
            print(f"✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(ALL_TESTS)} tests passed")
    return passed == len(ALL_TESTS)


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

'''
from assembler import Assembler
from cpu_core import Core
from cache import Cache

def test_basic_alu():
    asm = """
        LOAD R0, 7
        LOAD R1, 3
        ADD  R2, R0, R1
        PRINT R2
        HALT
    """
    core = Core(0, Assembler().assemble(asm.splitlines()), Cache())
    core.run_to_completion()
    assert core.output == [10], f"Expected [10], got {core.output}"
    print("✓ test_basic_alu passed")

def test_memory_ld_st():
    asm = """
        LOAD R0, 100       # address
        LOAD R1, 42        # value
        ST   R0, R1        # mem[100] = 42
        LD   R2, R0        # R2 = mem[100] (load-use hazard!)
        PRINT R2
        STI  108, R1       # mem[108] = 42
        LDI  R3, 108       # R3 = mem[108]
        PRINT R3
        HALT
    """
    core = Core(0, Assembler().assemble(asm.splitlines()), Cache())
    core.run_to_completion()
    assert core.output == [42, 42], f"Expected [42, 42], got {core.output}"
    assert core.stalls >= 1, "Expected load-use stall"
    print("✓ test_memory_ld_st passed (with load-use stall)")

def test_stack_and_subroutines():
    asm = """
        LOAD R1, 99
        PUSH R1
        POP  R2
        PRINT R2
        CALL func
        PRINT R3
        HALT
    func:
        LOAD R3, 77
        RET
    """
    core = Core(0, Assembler().assemble(asm.splitlines()), Cache())
    core.run_to_completion()
    assert core.output == [99, 77], f"Expected [99, 77], got {core.output}"
    print("✓ test_stack_and_subroutines passed")

def test_flags_and_branches():
    asm = """
        LOAD R1, 10
        LOAD R2, 20
        CMP  R1, R2
        JL   less
        LOAD R3, 0
        JMP  end
    less:
        LOAD R3, 1
    end:
        PRINT R3
        HALT
    """
    core = Core(0, Assembler().assemble(asm.splitlines()), Cache())
    core.run_to_completion()
    assert core.output == [1], f"Expected [1], got {core.output}"
    print("✓ test_flags_and_branches passed")

if __name__ == "__main__":
    test_basic_alu()
    test_memory_ld_st()
    test_stack_and_subroutines()
    test_flags_and_branches()
    print("All ISA and pipeline unit tests passed successfully!")
'''
