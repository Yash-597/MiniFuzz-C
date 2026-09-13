"""Delta-debugging reducer: shrinks a failing program to a minimal repro."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Callable

from .compilers import Config, compile_and_run, ub_guard
from .comparator import Mismatch

Pred = Callable[[list[str]], bool]


def ddmin(lines: list[str], test: Pred) -> list[str]:
    """Classic ddmin (complement version) over lines."""
    n = 2
    while len(lines) >= 2:
        chunk = -(-len(lines) // n)  # ceil
        for start in range(0, len(lines), chunk):
            candidate = lines[:start] + lines[start + chunk:]
            if candidate and test(candidate):
                lines = candidate
                n = max(n - 1, 2)
                break
        else:
            if chunk == 1:
                break
            n = min(len(lines), n * 2)
    return lines


def _match(lines: list[str], i: int) -> int | None:
    depth = 0
    for j in range(i, len(lines)):
        depth += lines[j].count("{") - lines[j].count("}")
        if depth == 0:
            return j
    return None


def remove_blocks(lines: list[str], test: Pred) -> list[str]:
    """Try deleting (or unwrapping) whole brace-balanced blocks."""
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.endswith("{") and not s.startswith("}") and not s.startswith("int main"):
            j = _match(lines, i)
            if j is not None:
                deleted = lines[:i] + lines[j + 1:]
                if test(deleted):
                    lines = deleted
                    continue
                unwrapped = lines[:i] + lines[i + 1:j] + lines[j + 1:]
                if test(unwrapped):
                    lines = unwrapped
                    continue
        i += 1
    return lines


_CONST = re.compile(r"\b(\d+)u\b")


def simplify_constants(lines: list[str], test: Pred) -> list[str]:
    """Replace literals by smaller ones (>1 -> 0 or 1, 1 -> 0). Only ever shrinks."""
    for idx in range(len(lines)):
        pos = 0
        while True:
            m = _CONST.search(lines[idx], pos)
            if not m:
                break
            value = int(m.group(1))
            options = ["0", "1"] if value > 1 else (["0"] if value == 1 else [])
            for repl in options:
                new_line = lines[idx][:m.start(1)] + repl + lines[idx][m.end(1):]
                candidate = lines[:idx] + [new_line] + lines[idx + 1:]
                if test(candidate):
                    lines = candidate
                    break
            pos = m.start(1) + 1
    return lines


class Reducer:
    def __init__(self, configs: list[Config], mismatch: Mismatch,
                 guard_cc: str = "gcc", sanitize: bool = True, verbose: bool = False):
        by_name = {c.name: c for c in configs}
        self.ref = by_name[mismatch.ref]
        self.bad = by_name[mismatch.bad]
        self.kind = mismatch.kind
        self.guard_cc = guard_cc
        self.sanitize = sanitize
        self.verbose = verbose
        self.cache: dict[str, bool] = {}
        self.tests = 0
        self.best = 0

    @staticmethod
    def _join(lines: list[str]) -> str:
        return "\n".join(lines) + "\n"

    def interesting(self, source: str) -> bool:
        if source not in self.cache:
            self.tests += 1
            self.cache[source] = self._check(source)
        return self.cache[source]

    def _check(self, source: str) -> bool:
        tmp = tempfile.mkdtemp(prefix="minifuzz_red_")
        try:
            d = Path(tmp)
            src = d / "prog.c"
            src.write_text(source)
            ref = compile_and_run(src, self.ref, d)
            if ref.status != "ok":
                return False
            bad = compile_and_run(src, self.bad, d)
            if self.kind == "output_diff":
                if bad.status != "ok" or bad.stdout == ref.stdout:
                    return False
            elif bad.status != self.kind:
                return False
            return ub_guard(src, d, self.guard_cc, self.sanitize)  # last: it is the slowest
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def _pred(self, lines: list[str]) -> bool:
        ok = self.interesting(self._join(lines))
        if ok and self.verbose and len(lines) < self.best:
            self.best = len(lines)
            print(f"  reduced to {self.best} lines ({self.tests} tests)")
        return ok

    def reduce(self, source: str) -> str:
        if not self.interesting(source):
            raise ValueError("original program does not reproduce the mismatch "
                             "(flaky, or rejected by the UB guard)")
        lines = source.splitlines()
        self.best = len(lines)
        while True:
            before = list(lines)
            lines = remove_blocks(lines, self._pred)
            lines = ddmin(lines, self._pred)
            lines = simplify_constants(lines, self._pred)
            if lines == before:
                break
        return self._join(lines)
