"""Save findings as original.c / reduced.c / report.md."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .compilers import Config
from .comparator import Mismatch


def compiler_versions(configs: list[Config]) -> dict[str, str]:
    seen: dict[str, str] = {}
    for c in configs:
        key = " ".join(c.compiler)
        if key in seen:
            continue
        try:
            p = subprocess.run([*c.compiler, "--version"], capture_output=True,
                               text=True, timeout=10)
            text = (p.stdout or p.stderr).strip()
            seen[key] = text.splitlines()[0] if text else "unknown"
        except Exception:
            seen[key] = "unknown"
    return seen


def save_finding(out_dir, seed: int, original: str, reduced: str, mismatch: Mismatch,
                 configs: list[Config], results, versions: dict[str, str],
                 tests_run: int) -> Path:
    d = Path(out_dir) / f"seed_{seed}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "original.c").write_text(original)
    (d / "reduced.c").write_text(reduced)

    by_name = {c.name: c for c in configs}
    ref, bad = by_name[mismatch.ref], by_name[mismatch.bad]
    ref_res, bad_res = results[ref.name], results[bad.name]

    def cmd(c: Config) -> str:
        return " ".join([*c.compiler, *c.flags, "reduced.c", "-o", f"{c.name}.bin"])

    n0, n1 = len(original.splitlines()), len(reduced.splitlines())
    md = [
        f"# MiniFuzz finding: seed {seed}", "",
        f"- **Kind:** `{mismatch.kind}`",
        f"- **Reference:** `{ref.name}`",
        f"- **Differs in:** `{bad.name}`",
        f"- **Detail:** {mismatch.detail}",
        f"- **Size:** {n0} lines -> {n1} lines ({tests_run} reducer tests)",
        "", "## Compiler versions", "",
    ]
    md += [f"- `{k}`: {v}" for k, v in versions.items()]
    md += ["", "## Reproduce", "", "```bash",
           cmd(ref), f"./{ref.name}.bin",
           cmd(bad), f"./{bad.name}.bin",
           "```", "", "## Reduced program", "", "```c", reduced.rstrip(), "```", "",
           "## Output", "",
           f"Expected ({ref.name}):", "```", ref_res.stdout.rstrip(), "```",
           f"Actual ({bad.name}), status = {bad_res.status}:", "```",
           bad_res.stdout.rstrip(), "```", ""]
    (d / "report.md").write_text("\n".join(md))
    return d
