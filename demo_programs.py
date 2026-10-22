"""
Demo programs exercising memory instructions (LD, ST, LDI, STI),
stack & subroutines (CALL, RET, PUSH, POP, SP), flags & comparisons
(CMP, CMPI, JE, JNE, JL, JGE), and 5-stage pipeline hazards.
"""

from assembler import Assembler


def program_recursive_fibonacci(n):
    """Compute the n-th Fibonacci number recursively using stack frames.

    Demonstrates: CALL, RET, PUSH, POP, CMP/CMPI, JL, JE, ADD, ADDI.
    """
    asm = f"""
        LOAD R0, {n}        # Argument n
        CALL fib
        PRINT R1            # Return value
        HALT

    fib:
        CMPI R0, 1
        JL   ret_base
        JE   ret_base

        # Recursive case: fib(n-1) + fib(n-2)
        PUSH R0             # Save current n
        ADDI R0, R0, -1     # n - 1
        CALL fib            # fib(n-1) returns in R1
        POP  R0             # Restore n

        PUSH R1             # Save fib(n-1) on stack
        PUSH R0             # Save n again
        ADDI R0, R0, -2     # n - 2
        CALL fib            # fib(n-2) returns in R1
        POP  R0             # Restore n
        POP  R2             # Restore fib(n-1) into R2

        ADD  R1, R1, R2     # R1 = fib(n-2) + fib(n-1)
        RET

    ret_base:
        MOV  R1, R0
        RET
    """
    return Assembler().assemble(asm.splitlines())


def program_bubble_sort(seed):
    """In-memory bubble sort of 4 elements.

    Demonstrates: Memory load/store (LDI, STI, LD, ST), loops, comparison
    flags, conditional branching, and load-use stalls.
    """
    # Deterministic unsorted array based on seed
    v0 = (seed * 7 + 42) % 100
    v1 = (seed * 13 + 17) % 100
    v2 = (seed * 19 + 89) % 100
    v3 = (seed * 23 + 5) % 100

    base = 100 + (seed % 10) * 32

    asm = f"""
        # Load elements into memory at base addresses
        LOAD R1, {v0}
        STI  {base}, R1
        LOAD R1, {v1}
        STI  {base + 8}, R1
        LOAD R1, {v2}
        STI  {base + 16}, R1
        LOAD R1, {v3}
        STI  {base + 24}, R1

        # Bubble sort 4 elements (3 passes)
        LOAD R0, 3          # Outer loop pass count
    outer_loop:
        # Pass 1: Compare pair (0, 1)
        LDI  R1, {base}
        LDI  R2, {base + 8}
        CMP  R1, R2
        JL   pair1_sorted
        STI  {base}, R2
        STI  {base + 8}, R1
    pair1_sorted:
        # Pass 2: Compare pair (1, 2)
        LDI  R1, {base + 8}
        LDI  R2, {base + 16}
        CMP  R1, R2
        JL   pair2_sorted
        STI  {base + 8}, R2
        STI  {base + 16}, R1
    pair2_sorted:
        # Pass 3: Compare pair (2, 3)
        LDI  R1, {base + 16}
        LDI  R2, {base + 24}
        CMP  R1, R2
        JL   pair3_sorted
        STI  {base + 16}, R2
        STI  {base + 24}, R1
    pair3_sorted:
        ADDI R0, R0, -1
        JNZ  R0, outer_loop

        # Print sorted values from memory using pointer LD
        LOAD R10, {base}
        LD   R1, R10
        PRINT R1
        ADDI R10, R10, 8
        LD   R1, R10
        PRINT R1
        ADDI R10, R10, 8
        LD   R1, R10
        PRINT R1
        ADDI R10, R10, 8
        LD   R1, R10
        PRINT R1
        HALT
    """
    return Assembler().assemble(asm.splitlines())


def program_string_reverse(seed):
    """Reverse a 4-character ASCII sequence in memory using the stack.

    Demonstrates: Memory LDI/STI, stack PUSH/POP, pointer manipulation, and
    forwarding.
    """
    # Sample 4-character ASCII codes varied by seed (e.g. 'A','B','C','D')
    c0 = 65 + (seed % 10)
    c1 = 75 + (seed % 10)
    c2 = 80 + (seed % 10)
    c3 = 33 + (seed % 5)

    base = 200 + (seed % 10) * 32

    asm = f"""
        # Store characters into memory buffer
        LOAD R1, {c0}
        STI  {base}, R1
        LOAD R1, {c1}
        STI  {base + 8}, R1
        LOAD R1, {c2}
        STI  {base + 16}, R1
        LOAD R1, {c3}
        STI  {base + 24}, R1

        # Push characters onto the stack in order
        LDI  R1, {base}
        PUSH R1
        LDI  R1, {base + 8}
        PUSH R1
        LDI  R1, {base + 16}
        PUSH R1
        LDI  R1, {base + 24}
        PUSH R1

        # Pop from stack in LIFO reverse order and store back to memory
        POP  R1
        STI  {base}, R1
        POP  R1
        STI  {base + 8}, R1
        POP  R1
        STI  {base + 16}, R1
        POP  R1
        STI  {base + 24}, R1

        # Print the reversed string values
        LDI  R1, {base}
        PRINT R1
        LDI  R1, {base + 8}
        PRINT R1
        LDI  R1, {base + 16}
        PRINT R1
        LDI  R1, {base + 24}
        PRINT R1
        HALT
    """
    return Assembler().assemble(asm.splitlines())
