import shutil
import sys
from pathlib import Path

import pytest

from minifuzz.comparator import find_mismatch
from minifuzz.compilers import Config
from minifuzz.generator import generate_program
from minifuzz.reducer import Reducer

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
WRAPPER = Path(__file__).resolve().parent.parent / "demo" / "buggy_cc.py"


def test_finds_and_reduces_injected_bug():
    cfgs = [
        Config("gcc-O0", ("gcc",), ("-O0",)),
        Config("buggy-O3", (sys.executable, str(WRAPPER)), ("-O3",)),
    ]
    for seed in range(50):
        src = generate_program(seed)
        mm, _ = find_mismatch(src, cfgs)
        if mm and mm.kind == "output_diff":
            break
    else:
        pytest.fail("injected bug was never detected")

    reduced = Reducer(cfgs, mm, sanitize=False).reduce(src)
    assert len(reduced.splitlines()) < len(src.splitlines())
    mm2, _ = find_mismatch(reduced, cfgs)
    assert mm2 is not None and mm2.kind == "output_diff"
