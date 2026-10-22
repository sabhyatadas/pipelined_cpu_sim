"""
A 32-bit instruction assembler for our 64-bit CPU simulator.
Encodes human-readable assembly instructions into 32-bit packed integers
and provides decoding helpers using bitmasks.
"""

OPCODE_MAP = {
    "NOP": 0,
    "HALT": 1,
    "LOAD": 2,    # LOAD Rd, imm (Load immediate)
    "MOV": 3,     # MOV Rd, Rs
    "ADD": 4,     # ADD Rd, Rs1, Rs2
    "ADDI": 5,    # ADDI Rd, Rs1, imm
    "SUB": 6,     # SUB Rd, Rs1, Rs2
    "MUL": 7,     # MUL Rd, Rs1, Rs2
    "DIV": 8,     # DIV Rd, Rs1, Rs2
    "AND": 9,     # AND Rd, Rs1, Rs2
    "OR": 10,     # OR Rd, Rs1, Rs2
    "XOR": 11,    # XOR Rd, Rs1, Rs2
    "SHL": 12,    # SHL Rd, Rs1, imm
    "SHR": 13,    # SHR Rd, Rs1, imm
    "JMP": 14,    # JMP target
    "JNZ": 15,    # JNZ Rs, target
    "PRINT": 16,  # PRINT Rs
    "LD": 17,     # LD Rd, Rs (Rd = mem[Rs])
    "ST": 18,     # ST Rd, Rs (mem[Rd] = Rs)
    "LDI": 19,    # LDI Rd, addr (Rd = mem[addr])
    "STI": 20,    # STI addr, Rs (mem[addr] = Rs)
    "PUSH": 21,   # PUSH Rs (sp -= 8; mem[sp] = Rs)
    "POP": 22,    # POP Rd (Rd = mem[sp]; sp += 8)
    "CALL": 23,   # CALL target (push PC+1; PC = target)
    "RET": 24,    # RET (pop target; PC = target)
    "CMP": 25,    # CMP Rs1, Rs2 (sets zf, sf)
    "CMPI": 26,   # CMPI Rs1, imm (sets zf, sf)
    "JE": 27,     # JE target
    "JNE": 28,    # JNE target
    "JL": 29,     # JL target
    "JGE": 30,    # JGE target
}

REV_OPCODE_MAP = {v: k for k, v in OPCODE_MAP.items()}


def parse_reg(token):
    token = token.strip().upper()
    if token == "SP":
        return 31
    if token.startswith("R"):
        reg_num = int(token[1:])
        if 0 <= reg_num < 32:
            return reg_num
    raise ValueError(f"Invalid register name: {token}")


def pack_instruction(op, rd=0, rs1=0, rs2=0, imm=0, target=0):
    """Pack fields into a 32-bit unsigned integer."""
    opcode = OPCODE_MAP[op]
    # R-type: opcode(6), rd(5), rs1(5), rs2(5), unused(11)
    if op in ("ADD", "SUB", "MUL", "DIV", "AND", "OR", "XOR", "CMP"):
        return (
            ((opcode & 0x3F) << 26)
            | ((rd & 0x1F) << 21)
            | ((rs1 & 0x1F) << 16)
            | ((rs2 & 0x1F) << 11)
        )
    # J-type: opcode(6), unused(5), target(21)
    elif op in ("JMP", "CALL", "JE", "JNE", "JL", "JGE"):
        return ((opcode & 0x3F) << 26) | (target & 0x1FFFFF)
    # JNZ-type: opcode(6), unused(5), rs1(5), target(16)
    elif op == "JNZ":
        return ((opcode & 0x3F) << 26) | ((rs1 & 0x1F) << 16) | (target & 0xFFFF)
    # I-type: opcode(6), rd(5), rs1(5), imm(16)
    elif op in (
        "LOAD",
        "MOV",
        "ADDI",
        "SHL",
        "SHR",
        "PRINT",
        "LD",
        "ST",
        "LDI",
        "STI",
        "PUSH",
        "POP",
        "CMPI",
    ):
        return (
            ((opcode & 0x3F) << 26)
            | ((rd & 0x1F) << 21)
            | ((rs1 & 0x1F) << 16)
            | (imm & 0xFFFF)
        )
    # 0-operand: opcode(6)
    elif op in ("NOP", "HALT", "RET"):
        return (opcode & 0x3F) << 26
    else:
        raise ValueError(f"Unknown opcode for packing: {op}")


def decode_instruction(word):
    """Decode a 32-bit integer into its constituent fields using bit masks."""
    opcode_num = (word >> 26) & 0x3F
    rd = (word >> 21) & 0x1F
    rs1 = (word >> 16) & 0x1F
    rs2 = (word >> 11) & 0x1F

    raw_imm = word & 0xFFFF
    # Sign extend 16-bit immediate
    imm = raw_imm if raw_imm < 0x8000 else raw_imm - 0x10000

    target_21 = word & 0x1FFFFF
    target_16 = word & 0xFFFF

    op = REV_OPCODE_MAP.get(opcode_num, "UNKNOWN")
    target = target_16 if op == "JNZ" else target_21

    return {
        "op": op,
        "opcode_num": opcode_num,
        "rd": rd,
        "rs1": rs1,
        "rs2": rs2,
        "imm": imm,
        "target": target,
        "raw_word": word,
    }


class Assembler:
    def __init__(self):
        self.labels = {}
        self.instructions = []

    def assemble(self, lines):
        self.labels = {}
        self.instructions = []

        # First pass: strip comments, resolve label addresses
        cleaned = []
        for line in lines:
            line = line.split("#")[0].strip()
            if not line:
                continue
            if line.endswith(":"):
                label = line[:-1].strip()
                self.labels[label] = len(cleaned)
            else:
                cleaned.append(line)

        def resolve_target(token):
            token = token.strip()
            if token in self.labels:
                return self.labels[token]
            return int(token)

        # Second pass: encode into 32-bit integers
        for line in cleaned:
            parts = line.replace(",", " ").split()
            op = parts[0].upper()

            if op not in OPCODE_MAP:
                raise ValueError(f"Unknown instruction opcode: {op} in '{line}'")

            if op == "LOAD":
                rd = parse_reg(parts[1])
                val = int(parts[2])
                self.instructions.append(pack_instruction("LOAD", rd=rd, imm=val))
            elif op == "MOV":
                rd = parse_reg(parts[1])
                rs = parse_reg(parts[2])
                self.instructions.append(pack_instruction("MOV", rd=rd, rs1=rs))
            elif op in ("ADD", "SUB", "MUL", "DIV", "AND", "OR", "XOR"):
                rd = parse_reg(parts[1])
                rs1 = parse_reg(parts[2])
                rs2 = parse_reg(parts[3])
                self.instructions.append(
                    pack_instruction(op, rd=rd, rs1=rs1, rs2=rs2)
                )
            elif op == "ADDI":
                rd = parse_reg(parts[1])
                rs1 = parse_reg(parts[2])
                imm = int(parts[3])
                self.instructions.append(
                    pack_instruction("ADDI", rd=rd, rs1=rs1, imm=imm)
                )
            elif op in ("SHL", "SHR"):
                rd = parse_reg(parts[1])
                rs1 = parse_reg(parts[2])
                imm = int(parts[3])
                self.instructions.append(
                    pack_instruction(op, rd=rd, rs1=rs1, imm=imm)
                )
            elif op == "JMP":
                target = resolve_target(parts[1])
                self.instructions.append(pack_instruction("JMP", target=target))
            elif op == "JNZ":
                rs = parse_reg(parts[1])
                target = resolve_target(parts[2])
                self.instructions.append(
                    pack_instruction("JNZ", rs1=rs, target=target)
                )
            elif op == "PRINT":
                rs = parse_reg(parts[1])
                self.instructions.append(pack_instruction("PRINT", rs1=rs))
            elif op == "HALT":
                self.instructions.append(pack_instruction("HALT"))
            elif op == "NOP":
                self.instructions.append(pack_instruction("NOP"))
            elif op == "LD":
                # LD Rd, Rs -> Rd = mem[Rs]
                rd = parse_reg(parts[1])
                rs = parse_reg(parts[2])
                self.instructions.append(pack_instruction("LD", rd=rd, rs1=rs))
            elif op == "ST":
                # ST Rd, Rs -> mem[Rd] = Rs
                rd = parse_reg(parts[1])
                rs = parse_reg(parts[2])
                self.instructions.append(pack_instruction("ST", rd=rd, rs1=rs))
            elif op == "LDI":
                # LDI Rd, addr -> Rd = mem[addr]
                rd = parse_reg(parts[1])
                addr = int(parts[2])
                self.instructions.append(pack_instruction("LDI", rd=rd, imm=addr))
            elif op == "STI":
                # STI addr, Rs -> mem[addr] = Rs
                addr = int(parts[1])
                rs = parse_reg(parts[2])
                self.instructions.append(pack_instruction("STI", rs1=rs, imm=addr))
            elif op == "PUSH":
                rs = parse_reg(parts[1])
                self.instructions.append(pack_instruction("PUSH", rs1=rs))
            elif op == "POP":
                rd = parse_reg(parts[1])
                self.instructions.append(pack_instruction("POP", rd=rd))
            elif op == "CALL":
                target = resolve_target(parts[1])
                self.instructions.append(pack_instruction("CALL", target=target))
            elif op == "RET":
                self.instructions.append(pack_instruction("RET"))
            elif op == "CMP":
                rs1 = parse_reg(parts[1])
                rs2 = parse_reg(parts[2])
                self.instructions.append(pack_instruction("CMP", rs1=rs1, rs2=rs2))
            elif op == "CMPI":
                rs1 = parse_reg(parts[1])
                imm = int(parts[2])
                self.instructions.append(pack_instruction("CMPI", rs1=rs1, imm=imm))
            elif op in ("JE", "JNE", "JL", "JGE"):
                target = resolve_target(parts[1])
                self.instructions.append(pack_instruction(op, target=target))
            else:
                raise ValueError(f"Unknown instruction: {line}")

        return self.instructions