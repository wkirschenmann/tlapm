#!/usr/bin/env python3
"""Subset-invariant checker over golden obligation dumps (see obldump.sh).

Usage:
    oblcheck.py [--strict|--subset] <baseline-dir> <candidate-dir>

Modes:
  --strict (default)
      generated.txt and shipped.txt must both be identical between baseline
      and candidate (same obligation locations, same block content, volatile
      fields already normalized out by obldump.sh).
      Required for every output-preserving change.

  --subset
      generated.txt must be identical (no new or changed obligations).
      In shipped.txt, per obligation location: the goal must be identical
      and every hypothesis line of the candidate must appear among the
      baseline's hypothesis lines (line-based, whitespace-stripped).
      Only for explicitly-flagged pruning changes.

Exit code 0 = pass, 1 = differences found, 2 = usage/IO error.
"""

import sys
import os


def parse_blocks(path):
    """Return {loc: block} where block = (fields dict, obl text or None)."""
    if not os.path.exists(path):
        raise IOError(f"missing dump file: {path}")
    with open(path) as f:
        content = f.read()
    blocks = {}
    for raw in content.split("@!!END"):
        raw = raw.strip("\n")
        if not raw.strip():
            continue
        fields = {}
        obl_lines = None
        for line in raw.split("\n"):
            if obl_lines is not None:
                obl_lines.append(line)
            elif line.startswith("@!!obl:"):
                obl_lines = [line[len("@!!obl:"):]]
            elif line.startswith("@!!"):
                key, _, val = line[3:].partition(":")
                fields[key] = val
        if fields.get("type") != "obligation":
            continue
        loc = fields.get("loc")
        if loc is None:
            continue
        obl = "\n".join(obl_lines) if obl_lines is not None else None
        if loc in blocks:
            # Two obligations can share a location (e.g. multiple obligations
            # from one step); disambiguate by order of appearance.
            i = 2
            while f"{loc}#{i}" in blocks:
                i += 1
            loc = f"{loc}#{i}"
        blocks[loc] = (fields, obl)
    return blocks


def split_sequent(obl):
    """Split a pretty-printed obligation into (hypothesis lines, goal lines).

    The printer emits either "ASSUME ... PROVE <goal>" or a bare goal.
    Line-based and conservative: if no PROVE line is found, everything is
    the goal.
    """
    lines = [ln.strip() for ln in obl.split("\n") if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith("PROVE"):
            return lines[:i], lines[i:]
    return [], lines


def norm_block(fields, obl):
    items = sorted((k, v) for k, v in fields.items())
    return (tuple(items), obl)


def check_identical(name, base, cand, errors):
    b_keys, c_keys = set(base), set(cand)
    for loc in sorted(c_keys - b_keys):
        errors.append(f"{name}: NEW obligation at {loc} (not in baseline)")
    for loc in sorted(b_keys - c_keys):
        errors.append(f"{name}: obligation at {loc} disappeared")
    for loc in sorted(b_keys & c_keys):
        if norm_block(*base[loc]) != norm_block(*cand[loc]):
            errors.append(f"{name}: obligation at {loc} differs")


def check_subset(base, cand, errors):
    b_keys, c_keys = set(base), set(cand)
    for loc in sorted(c_keys - b_keys):
        errors.append(f"shipped: NEW obligation at {loc} (not in baseline)")
    # A shipped obligation may legitimately disappear only if it also
    # disappeared from generated.txt — which the identical check on
    # generated already forbids — so a missing shipped block is suspicious.
    for loc in sorted(b_keys - c_keys):
        errors.append(f"shipped: obligation at {loc} no longer shipped")
    for loc in sorted(b_keys & c_keys):
        b_fields, b_obl = base[loc]
        c_fields, c_obl = cand[loc]
        if b_obl is None or c_obl is None:
            if norm_block(b_fields, b_obl) != norm_block(c_fields, c_obl):
                errors.append(f"shipped: {loc} differs (no obl text to "
                              f"compare — run dumps with --printallobs)")
            continue
        b_hyps, b_goal = split_sequent(b_obl)
        c_hyps, c_goal = split_sequent(c_obl)
        if b_goal != c_goal:
            errors.append(f"shipped: goal changed at {loc}")
        extra = [h for h in c_hyps if h not in b_hyps]
        if extra:
            errors.append(
                f"shipped: {loc} has {len(extra)} hypothesis line(s) not in "
                f"baseline, e.g. {extra[0][:80]!r}")


def main(argv):
    mode = "strict"
    args = []
    for a in argv[1:]:
        if a == "--strict":
            mode = "strict"
        elif a == "--subset":
            mode = "subset"
        else:
            args.append(a)
    if len(args) != 2:
        sys.stderr.write(__doc__)
        return 2
    base_dir, cand_dir = args

    try:
        base_gen = parse_blocks(os.path.join(base_dir, "generated.txt"))
        cand_gen = parse_blocks(os.path.join(cand_dir, "generated.txt"))
        base_shp = parse_blocks(os.path.join(base_dir, "shipped.txt"))
        cand_shp = parse_blocks(os.path.join(cand_dir, "shipped.txt"))
    except IOError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    errors = []
    check_identical("generated", base_gen, cand_gen, errors)
    if mode == "strict":
        check_identical("shipped", base_shp, cand_shp, errors)
    else:
        check_subset(base_shp, cand_shp, errors)

    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"oblcheck: {len(errors)} difference(s) [{mode}] "
              f"({len(base_gen)} baseline obligations)")
        return 1
    print(f"oblcheck: PASS [{mode}] generated={len(base_gen)} "
          f"shipped={len(base_shp)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
