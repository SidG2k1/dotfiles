"""Merge single-line top-level TOML preferences while preserving app-owned text."""
import argparse
from pathlib import Path
import re
import sys
import tomllib


def merge(source_text, target_text):
    source = tomllib.loads(source_text)
    target = tomllib.loads(target_text)
    assignments = {}
    pattern = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
    for line in source_text.splitlines(keepends=True):
        match = pattern.match(line)
        if match:
            key = match[1]
            value = source[key]
            if type(value) not in (str, int, float, bool) or tomllib.loads(line) != {key: value}:
                raise ValueError("merge-toml supports single-line scalar preferences only")
            assignments[key] = line.rstrip("\r\n") + "\n"
    if set(assignments) != set(source):
        raise ValueError("merge-toml supports bare top-level preference keys only")
    if all(key in target and type(target[key]) is type(value) and target[key] == value for key, value in source.items()):
        return target_text
    lines = target_text.splitlines(keepends=True)
    boundary = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    output = []
    for line in lines[:boundary]:
        match = pattern.match(line)
        if match and match[1] in assignments:
            output.append(assignments.pop(match[1]))
        else:
            output.append(line)
    if output and not output[-1].endswith("\n"):
        output[-1] += "\n"
    output.extend(assignments.values())
    output.extend(lines[boundary:])
    result = "".join(output)
    if tomllib.loads(result) != {**target, **source}:
        raise ValueError("cannot merge these preferences without changing app-owned fields")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        target = args.target.read_text() if args.target.exists() else ""
        result = merge(args.source.read_text(), target)
    except (OSError, ValueError) as error:
        print(f"merge-toml: {error}", file=sys.stderr)
        return 2
    if args.check:
        return 0 if result == target else 1
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
