"""Merge scalar TOML preferences in the root or named tables, preserving other text."""
import argparse
from pathlib import Path
import re
import sys
import tomllib


def merge(source_text, target_text):
    source = tomllib.loads(source_text)
    target = tomllib.loads(target_text)
    assignments = {"": {}}
    pattern = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
    table_pattern = re.compile(r"^\s*\[([A-Za-z0-9_-]+)\]\s*(?:#.*)?$")
    section = ""
    for line in source_text.splitlines(keepends=True):
        table = table_pattern.match(line)
        if table:
            section = table[1]
            assignments[section] = {}
            continue
        match = pattern.match(line)
        if match:
            key = match[1]
            value = (source[section] if section else source)[key]
            if type(value) not in (str, int, float, bool) or tomllib.loads(line) != {key: value}:
                raise ValueError("merge-toml supports single-line scalar preferences only")
            assignments[section][key] = line.rstrip("\r\n") + "\n"
        elif line.strip() and not line.lstrip().startswith("#"):
            raise ValueError("merge-toml supports bare keys and single-level tables only")
    expected = {**target, **source}
    for name in assignments:
        if not name:
            continue
        if name in target and not isinstance(target[name], dict):
            raise ValueError(f"cannot merge table [{name}] into a scalar")
        expected[name] = {**target.get(name, {}), **source[name]}
    output = []
    section = ""
    for line in target_text.splitlines(keepends=True):
        if line.lstrip().startswith("["):
            output.extend(assignments.pop(section, {}).values())
            table = table_pattern.match(line)
            section = table[1] if table else None
        match = pattern.match(line)
        if match and match[1] in assignments.get(section, {}):
            output.append(assignments[section].pop(match[1]))
        else:
            output.append(line)
    if output and not output[-1].endswith("\n"):
        output[-1] += "\n"
    output.extend(assignments.pop(section, {}).values())
    for name, values in assignments.items():
        if name:
            output.append(f"\n[{name}]\n")
        output.extend(values.values())
    result = "".join(output)
    if tomllib.loads(result) != expected:
        raise ValueError("cannot merge these preferences without changing app-owned fields")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--overlay", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        target = args.target.read_text() if args.target.exists() else ""
        result = merge(args.source.read_text(), target)
        for overlay in args.overlay:
            result = merge(overlay.read_text(), result)
    except (OSError, ValueError) as error:
        print(f"merge-toml: {error}", file=sys.stderr)
        return 2
    if args.check:
        return 0 if result == target else 1
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
