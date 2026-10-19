"""Fail if the repository contains an em dash, en dash or emoji in any tracked text file."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHES = {chr(0x2014): "em dash", chr(0x2013): "en dash"}
EMOJI_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B50, 0x2B55), (0xFE0F, 0xFE0F)]
EMOJI = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in EMOJI_RANGES) + "]")
SKIP_SUFFIX = {".png", ".pdf", ".pptx", ".ttf", ".woff", ".woff2", ".ico", ".parquet", ".duckdb", ".xml", ".json"}


def files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    keep = [ROOT / f for f in out if Path(f).suffix.lower() not in SKIP_SUFFIX]
    # Generated JSON we own (metrics) is checked too.
    keep += [ROOT / "reports" / "metrics.json"]
    return [p for p in keep if p.is_file()]


def main() -> int:
    bad = 0
    for p in files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for ch, name in DASHES.items():
                if ch in line:
                    print(f"{p.relative_to(ROOT)}:{n}: {name}")
                    bad += 1
            if EMOJI.search(line):
                print(f"{p.relative_to(ROOT)}:{n}: emoji or pictograph")
                bad += 1
    print("style check:", "clean" if not bad else f"{bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
