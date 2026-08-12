"""Compare the two capture pages' shared JavaScript functions.

docs/capture/index.html and scrim.html were forked, not shared: 104 named
functions exist in both and many have drifted. Engine extraction has to know
which, so it reconciles deliberately instead of silently picking one copy.

    .venv/Scripts/python.exe tools/capture_divergence.py
"""

from __future__ import annotations

import re
from pathlib import Path

CAPTURE = Path(__file__).resolve().parents[1] / "docs" / "capture"
FUNC = re.compile(r"(?:^|\s)(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(")


def function_bodies(filename: str) -> dict[str, str]:
    """Map every top-level named function to its brace-balanced body."""
    src = (CAPTURE / filename).read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in FUNC.finditer(src):
        start = src.index("{", m.end() - 1)
        depth, i = 0, start
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[m.group(1)] = src[start : i + 1]
    return out


def _norm(body: str) -> str:
    return re.sub(r"\s+", " ", body).strip()


def report() -> dict[str, list[str]]:
    a, b = function_bodies("index.html"), function_bodies("scrim.html")
    shared = sorted(set(a) & set(b))
    return {
        "shared": shared,
        "identical": [n for n in shared if _norm(a[n]) == _norm(b[n])],
        "diverged": [n for n in shared if _norm(a[n]) != _norm(b[n])],
    }


def main() -> None:
    rep = report()
    print(f"shared: {len(rep['shared'])}  "
          f"identical: {len(rep['identical'])}  "
          f"diverged: {len(rep['diverged'])}")
    a, b = function_bodies("index.html"), function_bodies("scrim.html")
    print("\nDIVERGED (name, index chars, scrim chars):")
    for n in sorted(rep["diverged"], key=lambda n: -abs(len(a[n]) - len(b[n]))):
        print(f"  {n:24} {len(a[n]):6} {len(b[n]):6}  {len(b[n]) - len(a[n]):+6}")


if __name__ == "__main__":
    main()
