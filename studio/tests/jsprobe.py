"""Evaluate pure functions sliced straight out of the shipped app.js under node.

app.js has no build step and no module system — it is one script the daemon
serves verbatim. To test a decision function without a browser we cut it out of
the file by brace matching and run it in node, so a test can never drift from
the code the browser actually gets.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def slice_fn(src: str, name: str) -> str:
    """Return the source of `function <name>(…) {…}`, matched by brace depth."""
    start = src.index("function %s(" % name)
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unbalanced braces in %s" % name)


def top_const(src: str, name: str) -> str:
    """Return the single-line top-level `const <name> = …;` declaration."""
    for line in src.split("\n"):
        if line.startswith("const %s " % name):
            return line
    raise AssertionError("%s must be a top-level const in app.js" % name)


def call(names, consts, expr):
    """Run `expr` in node with the named app.js functions/consts in scope."""
    src = APP_JS.read_text(encoding="utf-8")
    parts = [top_const(src, c) for c in consts]
    parts += [slice_fn(src, n) for n in names]
    parts.append("console.log(JSON.stringify(%s));" % expr)
    out = subprocess.run(["node", "-e", "\n".join(parts)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)
