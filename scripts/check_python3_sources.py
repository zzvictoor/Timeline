#!/usr/bin/env python3
"""Compile modern modules directly and legacy modules after the compat transform."""

from pathlib import Path
from lib2to3 import refactor
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]

MODERNIZED = {
    "Timeline/__init__.py",
    "Timeline/compat.py",
    "Timeline/Database/__init__.py",
    "Timeline/Database/DB.py",
    "Timeline/Handlers/Login.py",
    "Timeline/Handlers/Messages.py",
    "Timeline/Server/Constants.py",
    "Timeline/Server/Engine.py",
    "Timeline/Server/Packets.py",
    "Timeline/Server/Penguin.py",
    "Timeline/Server/Redis.py",
    "Timeline/Utils/Cryptography.py",
    "Timeline/Utils/Modules.py",
    "Start.py",
}

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    tool = refactor.RefactoringTool(refactor.get_fixers_from_package("lib2to3.fixes"))


def compile_source(path: Path, legacy: bool):
    source = path.read_text(encoding="utf-8-sig")
    if source and not source.endswith("\n"):
        source += "\n"
    if legacy:
        source = str(tool.refactor_string(source, str(path)))
    compile(source, str(path), "exec")


def main():
    failures = []
    paths = [ROOT / "Start.py", ROOT / "DatabasePort.py"]
    paths.extend(sorted((ROOT / "Timeline").rglob("*.py")))

    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        legacy = rel not in MODERNIZED
        try:
            compile_source(path, legacy)
            print("OK  {}{}".format(rel, " [compat]" if legacy else ""))
        except Exception as exc:
            failures.append((rel, exc))
            print("ERR {}: {}".format(rel, exc), file=sys.stderr)

    if failures:
        print("\n{} source file(s) failed.".format(len(failures)), file=sys.stderr)
        return 1
    print("\nAll Timeline sources compile for the Python 3.11 migration runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
