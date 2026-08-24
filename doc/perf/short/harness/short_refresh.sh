#!/usr/bin/env bash
# Refresh the document from the campaign CSVs, commit and push if it changed.
set -u
S=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
R=$(git rev-parse --show-toplevel)
cd $R || exit 1
# Merge, never copy.  A plain cp destroys any row that exists only in the committed
# copy -- which is what happens after a scratch directory is rebuilt, and it silently
# deleted a whole measured line once.
#
# The union has to be keyed on the MEASUREMENT, not on the text of the line, because
# the committed copy is a transformed version of the campaign's: this script rewrites
# the sha column from git and renumbers the drift anchors.  Keying on the line would
# then see every anchor twice, which is exactly what a first attempt did.  So the key
# drops the sha and collapses every K phase to one family; two rows with the same key
# are the same run recorded twice.
for f in short_sweep.csv short_iterlat.csv short_keystroke.csv short_reps.csv short_phases.csv; do
  [ -f $S/$f ] || continue
  python3 - "$S/$f" "$R/doc/perf/short/$f" <<'PYMERGE'
import io, os, sys
src, dst = sys.argv[1], sys.argv[2]
def read(p):
    if not os.path.exists(p):
        return None, []
    ls = io.open(p, encoding="utf-8").read().replace("\r", "").rstrip("\n").split("\n")
    return (ls[0], [l for l in ls[1:] if l]) if ls else (None, [])
h1, a = read(src)
h2, b = read(dst)
if h1 is not None and h2 is not None and h1.strip() != h2.strip():
    sys.exit("MERGE_REFUSED %s: headers differ" % dst)
hdr = h1 or h2
cols = [c.strip() for c in hdr.split(",")]
sha_i = cols.index("sha") if "sha" in cols else None
ph_i = cols.index("phase") if "phase" in cols else None
def key(line):
    r = line.split(",")
    if ph_i is not None and r[ph_i].startswith("K"):
        r = list(r)
        r[ph_i] = "K"
    return tuple(v for i, v in enumerate(r) if i != sha_i)
seen, out = set(), []
for r in a + b:                      # the campaign's own rows win on a tie
    k = key(r)
    if k not in seen:
        seen.add(k)
        out.append(r)
io.open(dst, "w", encoding="utf-8").write("\n".join([hdr] + out) + "\n")
print("  merged %s: %d runs (%d from the campaign, %d committed, %d in both)"
      % (os.path.basename(dst), len(out), len(a), len(b), len(a) + len(b) - len(out)))
PYMERGE
done
python3 - <<'PY'
import subprocess, csv, os
shas = subprocess.check_output(["git","rev-list","--reverse","main..tlapm-perf-short"]).decode().split()
main = subprocess.check_output(["git","rev-parse","main"]).decode().strip()
m = {"p00": main, "p00b": main}
for i, s in enumerate(shas): m["p%02d" % (i+1)] = s
for f in ("short_sweep.csv","short_iterlat.csv","short_keystroke.csv"):
    p = os.path.join("doc/perf/short", f)
    if not os.path.exists(p): continue
    rows = list(csv.DictReader(open(p)))
    if not rows: continue
    fn = list(rows[0].keys())
    # A campaign restart resets the anchor counter, so K8..K48 can each name two
    # different readings.  The readings are distinct and valid; renumber them in
    # file order here rather than in the live CSV the campaign is appending to.
    k = 0
    for r in rows:
        w = m.get(r["point"])
        if w: r["sha"] = w
        if r.get("phase","").startswith("K"):
            k += 8
            r["phase"] = "K%d" % k
    with open(p,"w",newline="") as g:
        wr = csv.DictWriter(g, fieldnames=fn); wr.writeheader(); wr.writerows(rows)
PY
python3 doc/perf/short/linecheck.py
python3 doc/perf/short/mkshort.py > /dev/null || { echo "REFRESH_FAILED generator"; exit 1; }
rm -rf doc/perf/short/__pycache__
# This commit is only ever allowed to say "here are more measurements".  It used to
# `git add -A doc/perf`, which swept whatever reader or generator change happened to
# be in the tree into a commit whose message claims to be a data refresh -- four of
# them, in one afternoon, hiding a reader fix and a data correction.  So it now stages
# the data and the generated page only, and says plainly when code is left behind.
if ! git diff --quiet -- doc/perf/short/*.py doc/perf/short/harness; then
  echo "REFRESH_CODE_UNCOMMITTED: generator or reader changes are in the tree and are"
  echo "  NOT in this commit -- commit them yourself, with a message that says what"
  echo "  they change:"
  git diff --stat -- doc/perf/short/*.py doc/perf/short/harness | sed 's/^/    /'
fi
if git diff --quiet -- doc/perf/short/*.csv doc/perf/SHORT_PROPOSAL.html; then
  echo "REFRESH_NOCHANGE"; exit 0
fi
cells=$(awk -F, 'NR>1 && ($6!=-2 || $8!=-2)' doc/perf/short/short_sweep.csv | wc -l)
git add doc/perf/short/*.csv doc/perf/SHORT_PROPOSAL.html
git commit -q -m "doc/perf/short: refresh curves from the campaign ($cells sweep rows)" || true
BR=${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}
for i in 1 2 3 4; do git push -q origin "$BR" 2>/dev/null && break || sleep $((2**i)); done
echo "REFRESHED $cells sweep rows"
