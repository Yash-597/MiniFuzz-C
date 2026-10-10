"""Random, UB-free C program generator.

Safety rules (so a difference between compilers means a compiler bug, not UB):
  * every value is uint32_t -> unsigned arithmetic wraps, it never overflows
  * division / modulo / shifts go through guarded helper functions
  * array indices are always reduced modulo the array size
  * every variable and array element is initialised
  * loops have small constant bounds, so programs always terminate

Each statement sits on its own line so the reducer can work line by line.
"""
from __future__ import annotations

import random

ARR = 8
BINOPS = ["+", "-", "*", "&", "|", "^"]
CMPS = ["<", "<=", ">", ">=", "==", "!="]
SAFE_CALLS = ["sdiv", "smod", "shl", "shr"]

PRELUDE = [
    "#include <stdio.h>",
    "#include <stdint.h>",
    "static uint32_t sdiv(uint32_t a, uint32_t b) { return b ? a / b : a; }",
    "static uint32_t smod(uint32_t a, uint32_t b) { return b ? a % b : a; }",
    "static uint32_t shl(uint32_t a, uint32_t b) { return a << (b & 31u); }",
    "static uint32_t shr(uint32_t a, uint32_t b) { return a >> (b & 31u); }",
]


class ProgramGenerator:
    def __init__(self, seed: int, n_vars: int = 6, n_stmts: int = 20,
                 max_depth: int = 2, n_funcs: int = 2):
        self.rng = random.Random(seed)
        self.vars = [f"v{i}" for i in range(n_vars)]
        self.n_stmts = n_stmts
        self.max_depth = max_depth
        self.n_funcs = n_funcs
        self.funcs: list[str] = []

    # ---------- expressions ----------
    def const(self) -> str:
        rng = self.rng
        pool = [0, 1, 2, 3, 5, 7, 8, 31, 255, 256, 65535,
                0x7FFFFFFF, 0x80000000, 0xFFFFFFFF]
        if rng.random() < 0.6:
            v = rng.choice(pool)
        else:
            v = rng.getrandbits(rng.choice([4, 8, 16, 32]))
        return f"{v}u"

    def expr(self, depth: int, names: list[str], arrays: bool = True) -> str:
        rng = self.rng
        if depth <= 0 or rng.random() < 0.2:
            return self.const() if rng.random() < 0.3 else rng.choice(names)

        kinds = ["bin", "call", "cond", "not"]
        weights = [50, 15, 10, 5]
        if arrays:
            kinds.append("arr")
            weights.append(10)
        if self.funcs:
            kinds.append("func")
            weights.append(15)
        kind = rng.choices(kinds, weights)[0]

        def sub() -> str:
            return self.expr(depth - 1, names, arrays)

        if kind == "bin":
            return f"({sub()} {rng.choice(BINOPS)} {sub()})"
        if kind == "call":
            return f"{rng.choice(SAFE_CALLS)}({sub()}, {sub()})"
        if kind == "cond":
            return f"(({sub()} {rng.choice(CMPS)} {sub()}) ? {sub()} : {sub()})"
        if kind == "not":
            return f"(~{sub()})"
        if kind == "arr":
            return f"a[({sub()}) % {ARR}u]"
        return f"{rng.choice(self.funcs)}({sub()}, {sub()})"  # func

    # ---------- statements ----------
    def stmt(self, depth: int, indent: int, loopvars: list[str]) -> list[str]:
        rng = self.rng
        pad = "    " * indent
        names = self.vars + loopvars
        can_nest = depth < self.max_depth
        kind = rng.choices(
            ["assign", "compound", "arr", "if", "for"],
            [35, 25, 15, 12 if can_nest else 0, 13 if can_nest else 0],
        )[0]

        if kind == "assign":
            return [f"{pad}{rng.choice(self.vars)} = {self.expr(3, names)};"]
        if kind == "compound":
            op = rng.choice(["+=", "-=", "^=", "&=", "|=", "*="])
            return [f"{pad}{rng.choice(self.vars)} {op} {self.expr(3, names)};"]
        if kind == "arr":
            return [f"{pad}a[({self.expr(2, names)}) % {ARR}u] = {self.expr(3, names)};"]
        if kind == "if":
            cond = f"{self.expr(2, names)} {rng.choice(CMPS)} {self.expr(2, names)}"
            lines = [f"{pad}if ({cond}) {{"]
            lines += self.block(depth + 1, indent + 1, loopvars)
            if rng.random() < 0.4:
                lines.append(f"{pad}}} else {{")
                lines += self.block(depth + 1, indent + 1, loopvars)
            lines.append(f"{pad}}}")
            return lines
        # for loop
        var = f"i{depth}"
        bound = rng.randint(2, 9)
        lines = [f"{pad}for (uint32_t {var} = 0u; {var} < {bound}u; {var}++) {{"]
        lines += self.block(depth + 1, indent + 1, loopvars + [var])
        lines.append(f"{pad}}}")
        return lines

    def block(self, depth: int, indent: int, loopvars: list[str]) -> list[str]:
        out: list[str] = []
        for _ in range(self.rng.randint(1, 3)):
            out += self.stmt(depth, indent, loopvars)
        return out

    # ---------- whole program ----------
    def gen_funcs(self) -> list[str]:
        lines = []
        for k in range(self.n_funcs):
            name = f"f{k}"
            body = self.expr(3, ["x", "y"], arrays=False)
            lines.append(f"static uint32_t {name}(uint32_t x, uint32_t y) {{ return {body}; }}")
            self.funcs.append(name)  # only later functions may call this one
        return lines

    def generate(self) -> str:
        out = list(PRELUDE)
        out += self.gen_funcs()
        out.append("int main(void) {")
        for v in self.vars:
            out.append(f"    uint32_t {v} = {self.const()};")
        init = ", ".join(self.const() for _ in range(ARR))
        out.append(f"    uint32_t a[{ARR}] = {{{init}}};")
        for _ in range(self.n_stmts):
            out += self.stmt(0, 1, [])
        for v in self.vars:
            out.append(f'    printf("%u\\n", (unsigned){v});')
        out.append(f'    for (uint32_t k = 0u; k < {ARR}u; k++) printf("%u\\n", (unsigned)a[k]);')
        out.append("    return 0;")
        out.append("}")
        return "\n".join(out) + "\n"


def generate_program(seed: int, **kwargs) -> str:
    return ProgramGenerator(seed, **kwargs).generate()
