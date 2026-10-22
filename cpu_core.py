"""
64-bit CPU core with a 5-stage pipeline (IF, ID, EX, MEM, WB),
data hazard detection (load-use stalls), forwarding unit,
branch penalty flushes, flags (ZF, SF), stack pointer (SP),
and memory hierarchy integration.
"""

import json
from assembler import decode_instruction, pack_instruction

with open("config.json") as f:
    CFG = json.load(f)

REG_BITS = CFG["register_bits"]
MASK = (1 << REG_BITS) - 1
NUM_REG = CFG["num_registers"]


def truncate(value):
    """Keep only the low 64 bits (unsigned wrapping)."""
    return value & MASK


class Core:
    def __init__(self, core_id, program, memory_hierarchy):
        self.core_id = core_id
        self.program = program  # list of 32-bit packed instruction ints
        self.memory = memory_hierarchy
        self.cache = (
            memory_hierarchy  # backward-compatibility alias for reporting
        )

        self.pc = 0
        self.halted = False
        self.output = []

        # 32 general-purpose 64-bit registers (R0..R31). R31 is SP.
        self.registers = [0] * NUM_REG
        # Distinct stack region per core to prevent stack collision
        self.registers[31] = 4096 + (self.core_id * 512)

        # Condition Flags
        self.zf = 0  # Zero Flag
        self.sf = 0  # Sign/Less-than Flag

        # Pipeline Registers
        self.if_id = None
        self.id_ex = None
        self.ex_mem = None
        self.mem_wb = None

        # Performance Counters
        self.cycles = 0
        self.instructions = 0
        self.stalls = 0
        self.flushes = 0

    @property
    def sp(self):
        return self.registers[31]

    @sp.setter
    def sp(self, val):
        self.registers[31] = truncate(val)

    def step(self):
        """Advance the 5-stage pipeline by one clock cycle.

        All pipeline registers are clocked concurrently.
        """
        if self.halted:
            return False

        self.cycles += 1

        # We compute next states for pipeline registers
        next_mem_wb = None
        next_ex_mem = None
        next_id_ex = None
        next_if_id = self.if_id
        stall_pipeline = False
        branch_taken = False
        branch_target = 0

        # =========================================================================
        # 1. WRITE-BACK (WB) STAGE
        # =========================================================================
        if self.mem_wb is not None:
            wb = self.mem_wb
            if wb["reg_write"]:
                self.registers[wb["rd"]] = truncate(wb["write_data"])

            if wb.get("is_print", False):
                self.output.append(wb["print_val"])

            if wb.get("is_halt", False):
                self.halted = True

            self.instructions += 1

        # If CPU halted in WB, finish step
        if self.halted:
            return False

        # =========================================================================
        # 2. MEMORY (MEM) STAGE
        # =========================================================================
        if self.ex_mem is not None:
            em = self.ex_mem
            write_data = em["alu_result"]

            if em["is_mem_read"]:
                val, _ = self.memory.read(em["mem_addr"])
                write_data = truncate(val)
            elif em["is_mem_write"]:
                self.memory.write(em["mem_addr"], em["store_val"])

            next_mem_wb = {
                "pc": em["pc"],
                "op": em["op"],
                "rd": em["rd"],
                "reg_write": em["reg_write"],
                "write_data": write_data,
                "is_print": em["is_print"],
                "print_val": em["print_val"],
                "is_halt": em["is_halt"],
            }

        # =========================================================================
        # 3. EXECUTE (EX) STAGE
        # =========================================================================
        if self.id_ex is not None:
            ie = self.id_ex
            op = ie["op"]

            # --- Forwarding Unit for operand 1 (rs1) ---
            op1 = ie["val1"]
            if ie["uses_rs1"]:
                if (
                    self.ex_mem
                    and self.ex_mem["reg_write"]
                    and self.ex_mem["rd"] == ie["rs1"]
                ):
                    op1 = self.ex_mem["alu_result"]
                elif (
                    self.mem_wb
                    and self.mem_wb["reg_write"]
                    and self.mem_wb["rd"] == ie["rs1"]
                ):
                    op1 = self.mem_wb["write_data"]

            # --- Forwarding Unit for operand 2 (rs2) ---
            op2 = ie["val2"]
            if ie["uses_rs2"]:
                if (
                    self.ex_mem
                    and self.ex_mem["reg_write"]
                    and self.ex_mem["rd"] == ie["rs2"]
                ):
                    op2 = self.ex_mem["alu_result"]
                elif (
                    self.mem_wb
                    and self.mem_wb["reg_write"]
                    and self.mem_wb["rd"] == ie["rs2"]
                ):
                    op2 = self.mem_wb["write_data"]

            # Forwarding for store target address (in rd for ST)
            val_rd = ie.get("val_rd", 0)
            if ie.get("uses_rd_as_src", False):
                if (
                    self.ex_mem
                    and self.ex_mem["reg_write"]
                    and self.ex_mem["rd"] == ie["rd"]
                ):
                    val_rd = self.ex_mem["alu_result"]
                elif (
                    self.mem_wb
                    and self.mem_wb["reg_write"]
                    and self.mem_wb["rd"] == ie["rd"]
                ):
                    val_rd = self.mem_wb["write_data"]

            alu_result = 0
            mem_addr = 0
            store_val = 0
            is_mem_read = ie["is_mem_read"]
            is_mem_write = ie["is_mem_write"]
            reg_write = ie["reg_write"]

            # --- ALU and Control Logic ---
            if op == "LOAD":
                alu_result = truncate(ie["imm"])
            elif op == "MOV":
                alu_result = truncate(op1)
            elif op == "ADD":
                alu_result = truncate(op1 + op2)
            elif op == "ADDI":
                alu_result = truncate(op1 + ie["imm"])
            elif op == "SUB":
                alu_result = truncate(op1 - op2)
            elif op == "MUL":
                alu_result = truncate(op1 * op2)
            elif op == "DIV":
                alu_result = 0 if op2 == 0 else truncate(op1 // op2)
            elif op == "AND":
                alu_result = truncate(op1 & op2)
            elif op == "OR":
                alu_result = truncate(op1 | op2)
            elif op == "XOR":
                alu_result = truncate(op1 ^ op2)
            elif op == "SHL":
                alu_result = truncate(op1 << (ie["imm"] & 63))
            elif op == "SHR":
                alu_result = truncate(op1 >> (ie["imm"] & 63))
            elif op == "CMP":
                self.zf = 1 if op1 == op2 else 0
                self.sf = 1 if op1 < op2 else 0
            elif op == "CMPI":
                self.zf = 1 if op1 == ie["imm"] else 0
                self.sf = 1 if op1 < ie["imm"] else 0
            elif op == "JMP":
                branch_taken = True
                branch_target = ie["target"]
            elif op == "JNZ":
                if op1 != 0:
                    branch_taken = True
                    branch_target = ie["target"]
            elif op == "JE":
                if self.zf == 1:
                    branch_taken = True
                    branch_target = ie["target"]
            elif op == "JNE":
                if self.zf == 0:
                    branch_taken = True
                    branch_target = ie["target"]
            elif op == "JL":
                if self.sf == 1:
                    branch_taken = True
                    branch_target = ie["target"]
            elif op == "JGE":
                if self.sf == 0:
                    branch_taken = True
                    branch_target = ie["target"]
            elif op == "CALL":
                # Push return address (PC + 1) onto stack, jump to target
                self.sp -= 8
                mem_addr = self.sp
                store_val = ie["pc"] + 1
                is_mem_write = True
                branch_taken = True
                branch_target = ie["target"]
            elif op == "RET":
                # Pop return address from stack, jump to target
                ret_addr, _ = self.memory.read(self.sp)
                self.sp += 8
                branch_taken = True
                branch_target = ret_addr
            elif op == "LD":
                mem_addr = op1
            elif op == "ST":
                mem_addr = val_rd
                store_val = op1
            elif op == "LDI":
                mem_addr = ie["imm"]
            elif op == "STI":
                mem_addr = ie["imm"]
                store_val = op1
            elif op == "PUSH":
                self.sp -= 8
                mem_addr = self.sp
                store_val = op1
            elif op == "POP":
                mem_addr = self.sp
                self.sp += 8

            next_ex_mem = {
                "pc": ie["pc"],
                "op": op,
                "rd": ie["rd"],
                "reg_write": reg_write,
                "alu_result": alu_result,
                "mem_addr": mem_addr,
                "store_val": store_val,
                "is_mem_read": is_mem_read,
                "is_mem_write": is_mem_write,
                "is_print": ie["is_print"],
                "print_val": op1 if ie["is_print"] else 0,
                "is_halt": ie["is_halt"],
            }

        # =========================================================================
        # 4. INSTRUCTION DECODE (ID) STAGE & HAZARD DETECTION
        # =========================================================================
        if self.if_id is not None:
            raw_word = self.if_id["raw_word"]
            dec = decode_instruction(raw_word)
            op = dec["op"]
            rd = dec["rd"]
            rs1 = dec["rs1"]
            rs2 = dec["rs2"]

            uses_rs1 = op in (
                "MOV",
                "ADD",
                "ADDI",
                "SUB",
                "MUL",
                "DIV",
                "AND",
                "OR",
                "XOR",
                "SHL",
                "SHR",
                "JNZ",
                "PRINT",
                "LD",
                "ST",
                "STI",
                "PUSH",
                "CMP",
                "CMPI",
            )
            uses_rs2 = op in (
                "ADD",
                "SUB",
                "MUL",
                "DIV",
                "AND",
                "OR",
                "XOR",
                "CMP",
            )
            uses_rd_as_src = op == "ST"
            reg_write = op in (
                "LOAD",
                "MOV",
                "ADD",
                "ADDI",
                "SUB",
                "MUL",
                "DIV",
                "AND",
                "OR",
                "XOR",
                "SHL",
                "SHR",
                "LD",
                "LDI",
                "POP",
            )
            is_mem_read = op in ("LD", "LDI", "POP")
            is_mem_write = op in ("ST", "STI", "PUSH")

            # --- Data Hazard Detection (Load-Use Stall) ---
            # If instruction currently in EX is loading from memory and ID needs its result:
            if self.id_ex is not None and self.id_ex["is_mem_read"]:
                load_rd = self.id_ex["rd"]
                if (
                    (uses_rs1 and rs1 == load_rd)
                    or (uses_rs2 and rs2 == load_rd)
                    or (uses_rd_as_src and rd == load_rd)
                ):
                    stall_pipeline = True
                    self.stalls += 1

            if not stall_pipeline:
                next_id_ex = {
                    "pc": self.if_id["pc"],
                    "op": op,
                    "rd": rd,
                    "rs1": rs1,
                    "rs2": rs2,
                    "val1": self.registers[rs1],
                    "val2": self.registers[rs2],
                    "val_rd": self.registers[rd] if uses_rd_as_src else 0,
                    "imm": dec["imm"],
                    "target": dec["target"],
                    "uses_rs1": uses_rs1,
                    "uses_rs2": uses_rs2,
                    "uses_rd_as_src": uses_rd_as_src,
                    "reg_write": reg_write,
                    "is_mem_read": is_mem_read,
                    "is_mem_write": is_mem_write,
                    "is_print": op == "PRINT",
                    "is_halt": op == "HALT",
                }
                next_if_id = None
            else:
                # Stall: insert bubble into EX, preserve IF/ID
                next_id_ex = None
                next_if_id = self.if_id

        # =========================================================================
        # 5. INSTRUCTION FETCH (IF) STAGE & BRANCH RESOLUTION
        # =========================================================================
        if branch_taken:
            # Branch Penalty: Flush both ID and IF stages
            self.pc = branch_target
            next_id_ex = None
            next_if_id = None
            self.flushes += 1
        elif not stall_pipeline:
            if 0 <= self.pc < len(self.program):
                raw_word = self.program[self.pc]
                # Instruction fetch access to cache
                self.memory.read(self.pc * 4)
                next_if_id = {"pc": self.pc, "raw_word": raw_word}
                self.pc += 1
            else:
                next_if_id = None

        # Clock the pipeline registers
        self.mem_wb = next_mem_wb
        self.ex_mem = next_ex_mem
        self.id_ex = next_id_ex
        self.if_id = next_if_id

        # Check if pipeline is completely drained
        if (
            self.pc >= len(self.program)
            and self.if_id is None
            and self.id_ex is None
            and self.ex_mem is None
            and self.mem_wb is None
        ):
            self.halted = True

        return not self.halted

    def run_to_completion(self):
        while not self.halted and self.cycles < CFG.get("max_cycles", 50000):
            self.step()
        return self.output
