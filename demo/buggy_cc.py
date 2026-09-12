#!/usr/bin/env python3
"""Fake 'buggy compiler' for demos: wraps gcc, but at -O3 it miscompiles ' ^ ' as ' | '."""
import os
import shutil
import subprocess
import sys
import tempfile

args = sys.argv[1:]
tmpdir = None
if "-O3" in args:
    tmpdir = tempfile.mkdtemp()
    patched = []
    for a in args:
        if a.endswith(".c") and os.path.exists(a):
            with open(a) as f:
                code = f.read().replace(" ^ ", " | ")
            p = os.path.join(tmpdir, os.path.basename(a))
            with open(p, "w") as f:
                f.write(code)
            patched.append(p)
        else:
            patched.append(a)
    args = patched
try:
    sys.exit(subprocess.call(["gcc"] + args))
finally:
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
