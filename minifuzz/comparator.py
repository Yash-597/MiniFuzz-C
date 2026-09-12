"""Run one program under every configuration and compare the results."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .compilers import Config, RunResult, compile_and_run


@dataclass
class Mismatch:
    kind: str     # output_diff | crash | timeout | compile_error | reference_failed
    ref: str
    bad: str
    detail: str


def first_diff(expected: str, actual: str) -> str:
    a, b = expected.splitlines(), actual.splitlines()
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"output line {i + 1}: expected {x!r}, got {y!r}"
    return f"output length differs: {len(a)} vs {len(b)} lines"


def run_all(source: str, configs: list[Config], workdir: Path) -> dict[str, RunResult]:
    src = workdir / "prog.c"
    src.write_text(source)
    return {c.name: compile_and_run(src, c, workdir) for c in configs}


def compare(results: dict[str, RunResult], configs: list[Config]) -> Mismatch | None:
    ref_cfg = configs[0]
    ref = results[ref_cfg.name]
    if ref.status != "ok":
        return Mismatch("reference_failed", ref_cfg.name, ref_cfg.name,
                        f"{ref.status}: {ref.detail}")
    for cfg in configs[1:]:
        res = results[cfg.name]
        if res.status != "ok":
            return Mismatch(res.status, ref_cfg.name, cfg.name, res.detail)
        if res.stdout != ref.stdout:
            return Mismatch("output_diff", ref_cfg.name, cfg.name,
                            first_diff(ref.stdout, res.stdout))
    return None


def find_mismatch(source: str, configs: list[Config]):
    d = tempfile.mkdtemp(prefix="minifuzz_")
    try:
        results = run_all(source, configs, Path(d))
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    return compare(results, configs), results
