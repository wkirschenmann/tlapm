#!/usr/bin/env python3
"""Generate instance_demo/L2Proofs.tla -- the level-2 proof module.

The corpus needs a proof shaped like a real one, not a wall of flat BYs,
because the quantities being measured depend on proof structure: tlapm emits
one obligation per leaf, and every step's statement joins the context of its
later siblings and of everything nested beneath it.  A tree of depth five
therefore costs quite differently from the same leaves laid out flat.

Two kinds of lemma, because they stress different things.

  CITING lemmas keep every operator opaque.  They chain implications between
  instantiated theorems, four or five levels deep.  What they exercise is the
  context: every definition of both levels below is carried, whether or not
  the goal mentions it.

  EXPANDING lemmas name definitions in DEF, so the bodies of the invariants
  really enter the obligation.  That is what a proof does when it opens an
  invariant to get at one conjunct, and it is the only way the weight of a
  definition reaches a prover at all.

Level-1 results are cited as L1!...  -- one INSTANCE hop.  Level-0 results as
L1!L0!...  -- two.  Each level-0 citation also needs L1!RefinesL0 to carry
L1!IndInv down, and both assumption bundles: an instantiated theorem carries
its home module's ASSUMEs renamed along the same path, so the hop depth of
the assumptions has to match the hop depth of the theorem.

Deterministic: the shape is a function of the lemma index, with no
randomness, so regenerating gives a byte-identical file.
"""
import os, sys

# Properties, by where they sit in the invariant -- which decides how many
# definitions a proof has to open to reach them.
L1_DIRECT = ["ArenaCoversQueue", "CreditMatchesArena", "ArenaRespectsPhase",
             "NoBufferOutlivesItsCall", "RefinementCoupling"]
L1_IN_CORE = ["BufferTypeOK", "HeldAgreesWithArena", "ChargeUnderCeiling"]
L0_DIRECT = ["JournalMentionsKnownIds", "ClosingDrains",
             "OwnedImpliesQueueable", "NoOrphanPayload"]
L0_IN_CORE = ["TypeOK", "SlotsAreNotShared", "PhaseMatchesLiveness",
              "QueueBounded"]
# Theorem k declares the k'th property, in the module's own order.
L1_ORDER = L1_IN_CORE + L1_DIRECT
L0_ORDER = L0_IN_CORE + L0_DIRECT

LEMMAS = int(sys.argv[1]) if len(sys.argv) > 1 else 40
EXPAND_EVERY = 3            # one lemma in three opens definitions
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "instance_demo", "L2Proofs.tla")


def conj(ms, ind):
    """One conjunct per line.  Real invariants are written this way -- 486 of
    the private stack's lines start with /\\ -- and a 200-column goal would
    make the generated file unreadable next to it."""
    return ["%s/\\ %s" % (" " * ind, prop(*m)) for m in ms]


def prop(kind, k):
    return ("L1!" if kind == "L1" else "L1!L0!") + \
           (L1_ORDER if kind == "L1" else L0_ORDER)[k]


def thm(kind, k):
    return ("L1!Q%d" if kind == "L1" else "L1!L0!P%d") % (k + 1) + "Holds"


def defs(kind, k):
    """The definitions a proof must open to reach this property from the
    invariant: one if it is a direct conjunct, two if it sits inside
    SafetyCore."""
    pre = "L1!" if kind == "L1" else "L1!L0!"
    inner = L1_IN_CORE if kind == "L1" else L0_IN_CORE
    d = [pre + "IndInv"]
    if (L1_ORDER if kind == "L1" else L0_ORDER)[k] in inner:
        d.append(pre + "SafetyCore")
    return d


def groups(i):
    """Groups of properties for lemma i.  Mixing L1 and L0 members inside one
    group is what forces both citation depths into the same subtree.  A
    property is taken at most once per lemma: a conjunction that repeats one
    is legal but would give two sibling steps with the same statement, which
    is not what a real proof looks like."""
    out, seen = [], set()
    n = i * 3
    for g in range(2 + i % 2):
        ms = []
        while len(ms) < 2 + (i + g) % 2:
            n += 1
            m = ("L1", n % 8) if n % 16 < 8 else ("L0", n % 8)
            if m not in seen:
                seen.add(m)
                ms.append(m)
        out.append(ms)
    return out


def citing_member(kind, k, ind):
    """Levels 3 to 5 for one property, everything opaque.

    Deliberately one step deeper than the logic needs: real proofs restate an
    antecedent before applying a theorem to it, and the restatement is what
    puts a statement into the context of everything nested below it.

    An L1 member cites one theorem at one hop and bottoms out at level four.
    An L0 member cites two at different hop depths and needs level five to
    combine them, so the file carries both."""
    o, p = [], " " * ind
    if kind == "L1":
        o += ["%s<3>1. L1!IndInv => %s" % (p, prop(kind, k)),
              "%s  <4>1. L1!IndInv => %s" % (p, prop(kind, k)),
              "%s    BY Asm, %s, Zenon" % (p, thm(kind, k)),
              "%s  <4>2. QED" % p,
              "%s    BY <4>1" % p,
              "%s<3>2. QED" % p,
              "%s  BY <3>1" % p]
    else:
        o += ["%s<3>1. L1!L0!IndInv => %s" % (p, prop(kind, k)),
              "%s  <4>1. %s" % (p, prop(kind, k)),
              "%s    <5>1. L1!L0!IndInv" % p,
              "%s      BY RefinesDown, Zenon" % p,
              "%s    <5>2. QED" % p,
              "%s      BY <5>1, Asm, AsmDown, %s, Zenon" % (p, thm(kind, k)),
              "%s  <4>2. QED" % p,
              "%s    BY <4>1" % p,
              "%s<3>2. QED" % p,
              "%s  BY <3>1, RefinesDown" % p]
    return o


def citing_lemma(i):
    gs = groups(i)
    flat = [m for g in gs for m in g]
    o = ["LEMMA Cite%d ==" % i,
         "    L1!IndInv =>"]
    o += conj(flat, 8)
    o += ["  <1> SUFFICES ASSUME L1!IndInv",
          "               PROVE"]
    o += conj(flat, 17)
    o += ["    OBVIOUS",
         "  <1>0. L1!L0!IndInv",
         "    BY RefinesDown, Zenon"]
    for gi, g in enumerate(gs, start=1):
        o.append("  <1>%d." % gi)
        o += conj(g, 8)
        for mi, (kind, k) in enumerate(g, start=1):
            o.append("    <2>%d. %s" % (mi, prop(kind, k)))
            o += citing_member(kind, k, 6)
        o.append("    <2>%d. QED" % (len(g) + 1))
        o.append("      BY %s" % ", ".join("<2>%d" % n
                                           for n in range(1, len(g) + 1)))
    o.append("  <1>%d. QED" % (len(gs) + 1))
    o.append("    BY %s" % ", ".join("<1>%d" % n
                                     for n in range(1, len(gs) + 1)))
    return o


def expanding_lemma(i):
    """Open the invariant and take one conjunct out of it, at both hop depths.

    This is the only kind of step whose obligation carries the BODIES of the
    definitions rather than their names, which is the whole reason the level
    modules define real invariants and not one-line predicates.

    Same depth discipline as a Cite lemma: the level-1 half bottoms out at
    four, the level-0 half needs five because the refinement has to be
    combined with the unfolding."""
    a = ("L1", (i * 5) % 8)
    b = ("L0", (i * 7 + 3) % 8)
    return ["LEMMA Open%d ==" % i,
            "    L1!IndInv =>",
            "        /\\ %s" % prop(*a),
            "        /\\ %s" % prop(*b),
            "  <1> SUFFICES ASSUME L1!IndInv",
            "               PROVE",
            "                 /\\ %s" % prop(*a),
            "                 /\\ %s" % prop(*b),
            "    OBVIOUS",
            "  <1>1. %s" % prop(*a),
            "    <2>1. L1!IndInv => %s" % prop(*a),
            "      <3>1. %s" % prop(*a),
            "        <4>1. L1!IndInv",
            "          OBVIOUS",
            "        <4>2. QED",
            "          BY <4>1 DEF %s" % ", ".join(defs(*a)),
            "      <3>2. QED",
            "        BY <3>1",
            "    <2>2. QED",
            "      BY <2>1",
            "  <1>2. %s" % prop(*b),
            "    <2>1. L1!L0!IndInv",
            "      BY RefinesDown, Zenon",
            "    <2>2. %s" % prop(*b),
            "      <3>1. L1!L0!IndInv => %s" % prop(*b),
            "        <4>1. ASSUME L1!L0!IndInv",
            "                     PROVE  %s" % prop(*b),
            "          <5>1. %s" % prop(*b),
            "            BY <4>1 DEF %s" % ", ".join(defs(*b)),
            "          <5>2. QED",
            "            BY <5>1",
            "        <4>2. QED",
            "          BY <4>1",
            "      <3>2. QED",
            "        BY <3>1, <2>1",
            "    <2>3. QED",
            "      BY <2>2",
            "  <1>3. QED",
            "    BY <1>1, <1>2"]


lines = ["------------------------- MODULE L2Proofs -------------------------",
         "(***************************************************************************)",
         ("(* Level 2's proof module: %d lemmas over the two levels below." % LEMMAS
          ).ljust(74) + "*)",
         "(*                                                                        *)",
         "(* Two kinds.  A Cite lemma keeps every operator opaque and chains          *)",
         "(* instantiated theorems four or five levels deep -- what it exercises is  *)",
         "(* the context, which carries every definition of both levels below        *)",
         "(* whether or not the goal mentions it.  An Open lemma names definitions   *)",
         "(* in DEF, so the bodies of the invariants really enter the obligation --  *)",
         "(* which is what a proof does when it opens an invariant to reach one      *)",
         "(* conjunct, and the only way a definition's weight reaches a prover.      *)",
         "(*                                                                        *)",
         "(* GENERATED by harness/gen_l2proofs.py -- do not edit by hand.  The shape *)",
         "(* is a function of the lemma index, with no randomness, so regenerating   *)",
         "(* is byte-identical and any diff means the generator changed.             *)",
         "(***************************************************************************)",
         "EXTENDS L2, TLAPS",
         "",
         "\\* The assumption bundle.  Every instantiated theorem below carries the",
         "\\* ASSUMEs of the module it came from as hypotheses of an ASSUME/PROVE, so",
         "\\* each citation has to discharge them.  Getting the hop count wrong here",
         "\\* is the mistake CiteTrap.tla is about: these assumptions reached level 1",
         "\\* by EXTENDS, so one INSTANCE hop later they are L1!IsFiniteSet, not",
         "\\* L1!L0!IsFiniteSet.",
         "LEMMA Asm ==",
         "    /\\ L1!IsFiniteSet(Ids) /\\ \"none\" \\notin Ids",
         "    /\\ L1!IsFiniteSet(Slots) /\\ Slots # {}",
         "    /\\ L1!IsFiniteSet(Buffers) /\\ Buffers # {}",
         "    /\\ Ceiling \\in Nat \\ {0}",
         "  BY FiniteIds, FiniteSlots, NoneNotAnId, FiniteBuffers, CeilingPositive,",
         "     Zenon",
         "  DEF L1!IsFiniteSet, IsFiniteSet",
         "",
         "\\* And the same bundle one hop further down, because the hop depth of the",
         "\\* assumptions equals the hop depth of the theorem being cited.  A level-0",
         "\\* theorem reached through level 1's own instance carries level 0's ASSUMEs",
         "\\* renamed twice, so Asm above does not discharge them and this one does.",
         "LEMMA AsmDown ==",
         "    /\\ L1!L0!IsFiniteSet(Ids) /\\ \"none\" \\notin Ids",
         "    /\\ L1!L0!IsFiniteSet(Slots) /\\ Slots # {}",
         "  BY FiniteIds, FiniteSlots, NoneNotAnId, Zenon",
         "  DEF L1!L0!IsFiniteSet, IsFiniteSet",
         "",
         "\\* Carried once and reused by every level-0 citation below: the refinement",
         "\\* is what lets a level-2 proof reach two INSTANCE hops down.",
         "LEMMA RefinesDown == L1!IndInv => L1!L0!IndInv",
         "  BY Asm, L1!RefinesL0, Zenon",
         ""]
for i in range(LEMMAS):
    lines += (expanding_lemma(i) if i % EXPAND_EVERY == 2 else citing_lemma(i))
    lines += [""]
lines.append("=====================================================================")
with open(OUT, "w") as f:
    f.write("\n".join(lines) + "\n")
n_open = sum(1 for i in range(LEMMAS) if i % EXPAND_EVERY == 2)
print("%s  %d lines, %d lemmas (%d citing, %d expanding)"
      % (os.path.normpath(OUT), len(lines), LEMMAS, LEMMAS - n_open, n_open))
