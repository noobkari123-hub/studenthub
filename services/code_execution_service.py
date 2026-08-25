"""
Best-effort sandboxed Python execution for the Coding Playground.

IMPORTANT — read before relying on this in production: this is NOT a
substitute for real container/VM isolation (Docker, gVisor, Firecracker,
or a hosted execution service like Judge0 or Piston). For a publicly
deployed site handling untrusted traffic, swap this out for one of
those. What this DOES provide, as defense in depth for a small/personal
deployment:

  - A static AST check that rejects imports and names outside a small
    safe allowlist (no os, sys, subprocess, socket, shutil, importlib,
    open, eval, exec, compile, __import__, ctypes, threading, ...).
  - Runs in a separate OS process, not inside the Flask process — a
    crash or resource spike there doesn't take down the server.
  - A hard wall-clock timeout.
  - On POSIX: CPU time, memory, process-count, and file-size limits via
    the `resource` module, plus `-I -S` (isolated mode, no site
    packages, no user site-packages) on the interpreter itself.

None of this guarantees perfect isolation — a sufficiently creative
sandbox-escape attempt could still get through. Don't expose this
without also putting it behind auth/rate-limiting, and prefer a real
container sandbox before taking untrusted public traffic at scale.
"""
import ast
import os
import subprocess
import sys
import tempfile

TIMEOUT_SECONDS = 5
MAX_OUTPUT_CHARS = 4000
MAX_CODE_LENGTH = 20000

_BLOCKED_NAMES = {
    "os", "sys", "subprocess", "socket", "shutil", "importlib", "ctypes",
    "multiprocessing", "threading", "pathlib", "glob", "pickle", "marshal",
    "open", "eval", "exec", "compile", "__import__", "input", "exit", "quit",
    "globals", "locals", "vars", "breakpoint", "help", "memoryview",
}
_BLOCKED_ATTRS = {"system", "popen", "remove", "rmdir", "unlink", "fork", "kill"}
_ALLOWED_IMPORTS = {
    "math", "random", "statistics", "itertools", "functools", "re",
    "string", "collections", "datetime", "json", "decimal", "fractions",
}


class UnsafeCodeError(Exception):
    pass


def _check_ast(code: str):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise UnsafeCodeError(f"Syntax error: {e}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in _ALLOWED_IMPORTS:
                    raise UnsafeCodeError(f"Import of '{alias.name}' isn't allowed in the playground sandbox.")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top not in _ALLOWED_IMPORTS:
                raise UnsafeCodeError(f"Import of '{node.module}' isn't allowed in the playground sandbox.")
        elif isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES:
            raise UnsafeCodeError(f"Use of '{node.id}' isn't allowed in the playground sandbox.")
        elif isinstance(node, ast.Attribute) and node.attr in _BLOCKED_ATTRS:
            raise UnsafeCodeError(f"Use of '.{node.attr}' isn't allowed in the playground sandbox.")


def _limit_resources():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    except Exception:
        pass  # best-effort — not available on all platforms (e.g. Windows)


def run_python(code: str) -> dict:
    """Returns {"stdout", "stderr", "timed_out", "blocked_reason"}."""
    if len(code) > MAX_CODE_LENGTH:
        return {"stdout": "", "stderr": "", "timed_out": False,
                "blocked_reason": "Code is too long for the playground."}
    try:
        _check_ast(code)
    except UnsafeCodeError as e:
        return {"stdout": "", "stderr": "", "timed_out": False, "blocked_reason": str(e)}

    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            path = f.name

        kwargs = {}
        if os.name == "posix":
            kwargs["preexec_fn"] = _limit_resources

        proc = subprocess.run(
            [sys.executable, "-I", "-S", path],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS, **kwargs,
        )
        # A negative returncode means the process was killed by a signal —
        # most often our own CPU/memory rlimit firing before the wall-clock
        # timeout would have. Surface that plainly instead of blank output.
        if proc.returncode is not None and proc.returncode < 0:
            return {"stdout": proc.stdout[:MAX_OUTPUT_CHARS], "stderr": "",
                    "timed_out": True, "blocked_reason": None}
        return {
            "stdout": proc.stdout[:MAX_OUTPUT_CHARS],
            "stderr": proc.stderr[:MAX_OUTPUT_CHARS],
            "timed_out": False, "blocked_reason": None,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "timed_out": True, "blocked_reason": None}
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
