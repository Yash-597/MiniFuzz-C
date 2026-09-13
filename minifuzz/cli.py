from __future__ import annotations

import argparse
import itertools
import os
import shutil
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .comparator import find_mismatch
from .compilers import Config, default_configs, ub_guard
from .generator import generate_program
from .reducer import Reducer
from .report import compiler_versions, save_finding


def build_configs(args) -> list[Config]:
    configs = [] if args.no_default_configs else default_configs()
    for spec in args.config or []:
        configs.append(Config.parse(spec))
    if len(configs) < 2:
        sys.exit("need at least 2 configurations (install gcc/clang or pass --config)")
    return configs


def check_toolchain(guard_cc: str, want_sanitize: bool) -> bool:
    if not shutil.which(guard_cc):
        sys.exit(f"guard compiler '{guard_cc}' not found (use --guard-cc)")
    if want_sanitize:
        d = tempfile.mkdtemp()
        try:
            p = Path(d) / "t.c"
            p.write_text("int main(void) { return 0; }\n")
            if not ub_guard(p, Path(d), guard_cc, True):
                print("warning: UBSan unavailable, using warnings-only UB guard")
                return False
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return want_sanitize


def is_ub_free(source: str, guard_cc: str, sanitize: bool) -> bool:
    d = tempfile.mkdtemp(prefix="minifuzz_ub_")
    try:
        p = Path(d) / "prog.c"
        p.write_text(source)
        return ub_guard(p, Path(d), guard_cc, sanitize)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def cmd_gen(args) -> None:
    src = generate_program(args.seed, n_stmts=args.stmts)
    if args.output:
        Path(args.output).write_text(src)
        print(f"wrote {args.output}")
    else:
        print(src, end="")


def cmd_fuzz(args) -> None:
    configs = build_configs(args)
    sanitize = check_toolchain(args.guard_cc, not args.no_sanitize)
    versions = compiler_versions(configs)
    print("Configurations (first is the reference):")
    for c in configs:
        print(f"  {c.name:<12} {' '.join(c.compiler)} {' '.join(c.flags)}")

    stats: Counter = Counter()
    findings = 0

    def work(seed: int):
        src = generate_program(seed, n_stmts=args.stmts)
        mm, _ = find_mismatch(src, configs)
        return seed, src, mm

    seeds = iter(range(args.seed_start, args.seed_start + args.count))
    done = False
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        while not done:
            batch = list(itertools.islice(seeds, args.jobs * 4))
            if not batch:
                break
            for seed, src, mm in pool.map(work, batch):
                stats["programs"] += 1
                if mm is None:
                    continue
                if mm.kind == "reference_failed":
                    stats["reference_failed"] += 1
                    continue
                if not is_ub_free(src, args.guard_cc, sanitize):
                    stats["suspect_ub"] += 1
                    continue

                print(f"[seed {seed}] mismatch ({mm.kind}): {mm.ref} vs {mm.bad}: {mm.detail}")
                reducer = Reducer(configs, mm, args.guard_cc, sanitize, verbose=True)
                try:
                    reduced = reducer.reduce(src)
                except ValueError as e:
                    print(f"  could not reduce: {e}")
                    stats["unreproducible"] += 1
                    continue
                _, rres = find_mismatch(reduced, configs)
                path = save_finding(args.out, seed, src, reduced, mm, configs,
                                    rres, versions, reducer.tests)
                stats["findings"] += 1
                findings += 1
                print(f"  saved -> {path}/report.md")
                if findings >= args.max_findings:
                    done = True
                    break
            print(f"  ... {stats['programs']} programs tested")

    print("\nSummary")
    for k in ("programs", "findings", "suspect_ub", "reference_failed", "unreproducible"):
        print(f"  {k:<18} {stats[k]}")


def cmd_reduce(args) -> None:
    configs = build_configs(args)
    sanitize = check_toolchain(args.guard_cc, not args.no_sanitize)
    source = Path(args.file).read_text()
    mm, _ = find_mismatch(source, configs)
    if mm is None or mm.kind == "reference_failed":
        sys.exit("no mismatch between configurations; nothing to reduce")
    print(f"mismatch ({mm.kind}): {mm.ref} vs {mm.bad}: {mm.detail}")
    reducer = Reducer(configs, mm, args.guard_cc, sanitize, verbose=True)
    reduced = reducer.reduce(source)
    out = Path(args.output) if args.output else Path(args.file).with_suffix(".reduced.c")
    out.write_text(reduced)
    print(f"wrote {out} ({len(reduced.splitlines())} lines, {reducer.tests} tests)")


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="minifuzz",
                                description="Differential compiler fuzzer with test-case reduction")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--config", action="append", metavar="NAME,COMPILER,FLAGS",
                        help="extra configuration, e.g. 'mycc-O3,mycc,-O3' (repeatable)")
        sp.add_argument("--no-default-configs", action="store_true")
        sp.add_argument("--guard-cc", default="gcc", help="compiler used for the UB guard")
        sp.add_argument("--no-sanitize", action="store_true", help="skip the UBSan check")

    g = sub.add_parser("gen", help="print a generated program")
    g.add_argument("seed", type=int)
    g.add_argument("--stmts", type=int, default=20)
    g.add_argument("-o", "--output")
    g.set_defaults(fn=cmd_gen)

    f = sub.add_parser("fuzz", help="generate, compare, reduce, report")
    common(f)
    f.add_argument("--count", type=int, default=100)
    f.add_argument("--seed-start", type=int, default=0)
    f.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    f.add_argument("--stmts", type=int, default=20)
    f.add_argument("--out", default="findings")
    f.add_argument("--max-findings", type=int, default=3)
    f.set_defaults(fn=cmd_fuzz)

    r = sub.add_parser("reduce", help="reduce an existing failing .c file")
    common(r)
    r.add_argument("file")
    r.add_argument("-o", "--output")
    r.set_defaults(fn=cmd_reduce)
    return p


def main(argv=None) -> None:
    args = make_parser().parse_args(argv)
    args.fn(args)
