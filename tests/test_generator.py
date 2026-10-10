import shutil
import subprocess

import pytest

from minifuzz.generator import generate_program

needs_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")


def test_deterministic():
    assert generate_program(7) == generate_program(7)
    assert generate_program(7) != generate_program(8)


@needs_gcc
def test_programs_compile_and_run(tmp_path):
    for seed in range(10):
        src = tmp_path / f"p{seed}.c"
        src.write_text(generate_program(seed))
        exe = tmp_path / f"p{seed}"
        subprocess.run(["gcc", "-O0", str(src), "-o", str(exe)], check=True)
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
        assert out.returncode == 0
        assert len(out.stdout.splitlines()) == 6 + 8  # 6 vars + 8 array cells
