"""Compiler configurations, compile+run helpers and the UB guard."""
from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Warnings that catch most UB that line-deletion can introduce
# (e.g. uninitialised reads). Unused-* warnings are expected after deletion.
GUARD_WARNINGS = [
    "-Wall", "-Wextra", "-Werror",
    "-Wno-unused", "-Wno-unused-parameter",
    "-Wno-type-limits", "-Wno-tautological-compare",
]


@dataclass(frozen=True)
class Config:
    name: str
    compiler: tuple[str, ...]
    flags: tuple[str, ...]

    @classmethod
    def parse(cls, spec: str) -> "Config":
        try:
            name, compiler, flags = spec.split(",", 2)
        except ValueError:
            raise ValueError(f"bad --config {spec!r}; expected NAME,COMPILER,FLAGS") from None
        return cls(name.strip(), tuple(shlex.split(compiler)), tuple(shlex.split(flags)))


@dataclass
class RunResult:
    status: str          # ok | compile_error | timeout | crash
    stdout: str = ""
    detail: str = ""


def default_configs() -> list[Config]:
    configs: list[Config] = []
    for cc, levels in (("gcc", ["-O0", "-O1", "-O2", "-O3", "-Os"]),
                       ("clang", ["-O0", "-O2", "-O3"])):
        if shutil.which(cc):
            for lvl in levels:
                configs.append(Config(f"{cc}{lvl}", (cc,), (lvl,)))
    return configs


def _run(cmd: list[str], timeout: int):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              errors="replace", timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None


def compile_and_run(src: Path, cfg: Config, workdir: Path,
                    compile_timeout: int = 60, run_timeout: int = 5) -> RunResult:
    exe = workdir / f"{cfg.name}.bin"
    cmd = [*cfg.compiler, *cfg.flags, str(src), "-o", str(exe)]
    p = _run(cmd, compile_timeout)
    if p is None:
        return RunResult("compile_error", detail="compiler timed out or could not start")
    if p.returncode != 0:
        return RunResult("compile_error", detail=p.stderr[-500:])
    q = _run([str(exe)], run_timeout)
    if q is None:
        return RunResult("timeout", detail=f"no exit within {run_timeout}s")
    if q.returncode != 0:
        return RunResult("crash", q.stdout, f"exit code {q.returncode}")
    return RunResult("ok", q.stdout)


def ub_guard(src: Path, workdir: Path, cc: str = "gcc", sanitize: bool = True) -> bool:
    """True if the program looks free of UB: compiles warning-free at -O2 and
    (optionally) runs clean under UBSan."""
    p = _run([cc, "-O2", "-c", *GUARD_WARNINGS, str(src), "-o", str(workdir / "guard.o")], 60)
    if p is None or p.returncode != 0:
        return False
    if sanitize:
        exe = workdir / "guard.bin"
        p = _run([cc, "-O0", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                  str(src), "-o", str(exe)], 60)
        if p is None or p.returncode != 0:
            return False
        q = _run([str(exe)], 5)
        if q is None or q.returncode != 0:
            return False
    return True
