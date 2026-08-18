#!/usr/bin/env python3
"""Generate a synthetic TLA+ proof module for tlapm performance measurements.

The generated module is deliberately shaped like the pathological real-world
specs analyzed in doc/perf/ANALYSIS.md:

  * ``--defs`` operator definitions.  Ordinary definitions are parsed Hidden
    (src/module/m_parser.ml:44); they only cost when cited via ``BY DEF``,
    which triggers expansion (src/backend/prep.ml:38-54).
  * ``--lemmas`` named lemmas.  Every named THEOREM/LEMMA becomes a *Visible*
    definition carrying its full statement in the context of all subsequent
    obligations (src/module/m_t.ml:153-160) — the Theta(N^2) context term.
  * ``--steps`` proof steps per lemma, each producing one obligation.
  * ``--cite`` definitions cited per ``BY DEF`` step (drives expansion cost).

All obligations are propositional trivialities, so the module is provable by
any backend (useful for M4 milestone runs) while remaining meaningful for the
solver-free M0-M3 levels.

Deterministic: same arguments, same output.
"""

import argparse
import sys


def generate(lemmas: int, steps: int, defs: int, cite: int) -> str:
    lines = []
    name = f"Synth_L{lemmas}_S{steps}_D{defs}_C{cite}"
    lines.append(f"---- MODULE {name} ----")
    lines.append("")

    # Hidden operator definitions. Each body references the previous
    # definition so that expansion is not trivially constant-size.
    lines.append(f"Def_0 == TRUE")
    for i in range(1, defs):
        lines.append(f"Def_{i} == Def_{i-1} /\\ TRUE")
    lines.append("")

    for j in range(lemmas):
        cited = [f"Def_{(j + t) % defs}" for t in range(min(cite, defs))]
        conj = " /\\ ".join(cited) if cited else "TRUE"
        lines.append(f"LEMMA Lem_{j} == {conj} => {cited[0] if cited else 'TRUE'}")
        step_names = []
        for s in range(steps - 1):
            step_names.append(f"<1>s{s}")
            if s % 2 == 0 and cited:
                # A BY DEF step: forces expansion of the cited definitions.
                lines.append(
                    f"<1>s{s}. {conj} => {cited[0]} BY DEF "
                    + ", ".join(cited)
                )
            else:
                lines.append(f"<1>s{s}. TRUE OBVIOUS")
        by = " BY " + step_names[0] if step_names else " OBVIOUS"
        lines.append(f"<1>q. QED{by}")
        lines.append("")

    lines.append("====")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lemmas", type=int, default=100)
    p.add_argument("--steps", type=int, default=5,
                   help="proof steps per lemma (>=1)")
    p.add_argument("--defs", type=int, default=50)
    p.add_argument("--cite", type=int, default=3,
                   help="definitions cited per BY DEF step")
    p.add_argument("--out", required=True,
                   help="output .tla path; the module name is derived from "
                        "the parameters, so the file name must match "
                        "(use the printed name), or pass --stdin to tlapm")
    args = p.parse_args()

    if args.steps < 1 or args.lemmas < 1 or args.defs < 1:
        p.error("--lemmas, --steps and --defs must be >= 1")

    text = generate(args.lemmas, args.steps, args.defs, args.cite)
    with open(args.out, "w") as f:
        f.write(text)

    name = text.splitlines()[0].split()[2]
    n_lines = text.count("\n")
    print(f"module={name} lines={n_lines} "
          f"lemmas={args.lemmas} steps={args.steps} "
          f"defs={args.defs} cite={args.cite}")
    if not args.out.endswith(f"{name}.tla"):
        print(f"note: tlapm requires the file to be named {name}.tla "
              f"(or feed it with --stdin {name})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
