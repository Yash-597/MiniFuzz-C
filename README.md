# MiniFuzz-C: Differential Compiler Verification Tool

MiniFuzz-C is an automated compiler testing tool designed to find optimization bugs in mature C compilers (like GCC and Clang) using **differential fuzzing**. It generates random, UB-free C programs, cross-compiles them across multiple optimization levels, and uses **Delta-Debugging** to automatically shrink failing programs into minimal reproducible test cases.

## Key Features
* **UB-Free Program Generation**: Generates complex, deterministic C code strictly avoiding Undefined Behavior by using guarded wrappers and unsigned arithmetic (validated via `-fsanitize=undefined`).
* **Differential Testing**: Cross-compiles programs across `gcc` and `clang` optimization levels (`-O0`, `-O1`, `-O2`, `-O3`, `-Os`) and detects optimization discrepancies by comparing execution outputs.
* **Delta-Debugging Reducer**: Automatically shrinks massive failing C programs down to a 20-30 line minimal reproducible snippet, significantly accelerating the debugging process for compiler engineers.
* **Multi-threaded Execution**: Scalable test-runner capable of validating thousands of randomly generated programs in parallel.

## How it Works
1. **Generate**: Writes a random C program (the "seed").
2. **Compile**: Passes the program through multiple compiler configurations.
3. **Compare**: Runs the compiled executables. If the standard outputs do not perfectly match the unoptimized reference (`-O0`), a bug is flagged.
4. **Reduce**: Iteratively deletes blocks, lines, and simplifies constants to isolate the exact logic triggering the optimization failure.

## Quickstart

### Prerequisites
* Python 3.9+
* `gcc` and/or `clang` installed in your PATH.

### Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage
Run the fuzzer with a set of configurations (e.g., finding bugs across 2000 seeds):
```bash
python3 -m minifuzz fuzz --count 2000 --jobs 8
```

Generate a single test program:
```bash
python3 -m minifuzz gen 42
```

Manually reduce a known failing C file:
```bash
python3 -m minifuzz reduce my_failing_test.c
```

## Example Finding
When MiniFuzz-C detects a discrepancy, it generates a full markdown report along with the original and reduced `.c` files.
```text
[seed 212] mismatch (timeout): gcc-O0 vs gcc-O2: no exit within 5s
  reduced to 51 lines (2 tests)
  reduced to 44 lines (16 tests)
...
  reduced to 21 lines (125 tests)
  saved -> findings/seed_212/report.md
```
