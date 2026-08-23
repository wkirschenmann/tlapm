#!/usr/bin/env python3
"""Generate instance_demo/L2Proofs.tla -- the level-2 proof module.

The corpus needs a proof that is *shaped* like a real one, not a wall of flat
BYs, because the quantities being measured depend on proof structure:
tlapm generates one obligation per leaf, and every step's statement joins the
context of its later siblings and of everything nested under them.  A tree of
depth five therefore costs quite differently from the same number of leaves
laid out flat, which is exactly what the corpus has to exercise.

Every lemma is a conjunction split down five levels:

  <1>  one step per group of properties, plus the level-0 antecedent
  <2>  one step per property inside a group
  <3>  separate 'the antecedent holds' from 'the theorem applies'
  <4>  the instantiated theorem, cited by name
  <5>  its two halves, for the level-0 properties reached through refinement

Level-1 properties are cited as L1!QkHolds -- one INSTANCE hop.  Level-0
properties are cited as L1!L0!PkHolds -- two hops -- and each needs
L1!RefinesL0 to carry L1!IndInv down to L1!L0!IndInv first.  That mix is the
point: it is the citation pattern of a refinement stack, and it is where the
prefix depth is easy to get wrong.

Deterministic: the shape is a function of the lemma index, no randomness, so
regenerating gives a byte-identical file.
"""
import os, sys

NL1, NL0 = 8, 8
LEMMAS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "instance_demo", "L2Proofs.tla")


def members(i):
    """Groups of properties for lemma i.  Mixing L1 and L0 members within a
    group is what forces the two citation depths into the same subtree."""
    groups = []
    for g in range(2 + i % 2):                       # two or three groups
        ms = []
        for k in range(2 + (i + g) % 2):             # two or three members
            n = (i * 3 + g * 2 + k) % (NL1 + NL0)
            ms.append(("L1", n % NL1 + 1) if n < NL1
                      else ("L0", n % NL0 + 1))
        groups.append(ms)
    return groups


def name(kind, k):
    return "L1!Q%d" % k if kind == "L1" else "L1!L0!P%d" % k


def thm(kind, k):
    return "L1!Q%dHolds" % k if kind == "L1" else "L1!L0!P%dHolds" % k


def member_proof(kind, k, ind):
    """Levels 3 to 5 for one property.  Deliberately one step deeper than the
    logic strictly needs: real proofs restate an antecedent before applying a
    theorem to it, and the restatement is what puts a statement into the
    context of everything nested below it -- which is the cost being measured.

    An L1 member cites one theorem, at one INSTANCE hop, and bottoms out at
    level four.  An L0 member cites two at different hop depths -- its own
    theorem, two hops down, and the refinement that carries L1!IndInv to
    L1!L0!IndInv -- and needs level five to combine them.  So the file
    carries both depths, which is what a real proof looks like."""
    o, p = [], " " * ind
    if kind == "L1":
        o.append("%s<3>1. L1!IndInv => %s" % (p, name(kind, k)))
        o.append("%s  <4>1. L1!IndInv => %s" % (p, name(kind, k)))
        o.append("%s    BY Asm, %s, Zenon" % (p, thm(kind, k)))
        o.append("%s  <4>2. QED" % p)
        o.append("%s    BY <4>1" % p)
        o.append("%s<3>2. QED" % p)
        o.append("%s  BY <3>1" % p)
    else:
        o.append("%s<3>1. L1!L0!IndInv => %s" % (p, name(kind, k)))
        o.append("%s  <4>1. %s" % (p, name(kind, k)))
        o.append("%s    <5>1. L1!L0!IndInv" % p)
        o.append("%s      BY RefinesDown, Zenon" % p)
        o.append("%s    <5>2. QED" % p)
        o.append("%s      BY <5>1, Asm, AsmDown, %s, Zenon" % (p, thm(kind, k)))
        o.append("%s  <4>2. QED" % p)
        o.append("%s    BY <4>1" % p)
        o.append("%s<3>2. QED" % p)
        o.append("%s  BY <3>1, RefinesDown" % p)
    return o


def lemma(i):
    gs = members(i)
    flat = [m for g in gs for m in g]
    goal = " /\\ ".join(name(*m) for m in flat)
    o = ["LEMMA Bundle%d ==" % i,
         "    L1!IndInv => %s" % goal,
         "  <1> SUFFICES ASSUME L1!IndInv",
         "               PROVE  %s" % goal,
         "    OBVIOUS",
         "  <1>0. L1!L0!IndInv",
         "    BY RefinesDown, Zenon"]
    for gi, g in enumerate(gs, start=1):
        o.append("  <1>%d. %s" % (gi, " /\\ ".join(name(*m) for m in g)))
        for mi, (kind, k) in enumerate(g, start=1):
            o.append("    <2>%d. %s" % (mi, name(kind, k)))
            o.extend(member_proof(kind, k, 6))
        o.append("    <2>%d. QED" % (len(g) + 1))
        o.append("      BY %s" % ", ".join("<2>%d" % n
                                           for n in range(1, len(g) + 1)))
    o.append("  <1>%d. QED" % (len(gs) + 1))
    o.append("    BY %s" % ", ".join("<1>%d" % n
                                     for n in range(1, len(gs) + 1)))
    return o


lines = ["------------------------- MODULE L2Proofs -------------------------",
         "(***************************************************************************)",
         ("(* Level 2's proof module: %d lemmas, every one a five-level tree," % LEMMAS).ljust(74) + "*)",
         "(* citing level 1 at one INSTANCE hop and level 0 at two.                  *)",
         "(*                                                                        *)",
         "(* GENERATED by harness/gen_l2proofs.py -- do not edit by hand.  The shape *)",
         "(* is a function of the lemma index, with no randomness, so regenerating   *)",
         "(* is byte-identical and any diff means the generator changed.             *)",
         "(***************************************************************************)",
         "EXTENDS L2, TLAPS",
         "",
         "\\* The assumption bundle.  Every instantiated theorem below carries the",
         "\\* ASSUMEs of the module it came from as hypotheses of an ASSUME/PROVE, so",
         "\\* each citation has to discharge them.  Stating them once and citing this",
         "\\* lemma is what a real refinement proof does -- and getting the INSTANCE",
         "\\* hop count wrong here is the mistake CiteTrap.tla is about: these",
         "\\* assumptions reached level 1 by EXTENDS, so one hop later they are",
         "\\* L1!IsFiniteSet, not L1!L0!IsFiniteSet.",
         "LEMMA Asm ==",
         "    /\\ L1!IsFiniteSet(Ids) /\\ \"none\" \\notin Ids",
         "    /\\ L1!IsFiniteSet(Buffers) /\\ Buffers # {}",
         "  BY FiniteIds, NoneNotAnId, FiniteBuffers, Zenon",
         "  DEF L1!IsFiniteSet, IsFiniteSet",
         "",
         "\\* And the same bundle one hop further down, because the hop count of the",
         "\\* assumptions equals the hop count of the theorem being cited.  A level-0",
         "\\* theorem reached through level 1's own instance carries level 0's ASSUMEs",
         "\\* renamed twice, so Asm above does not discharge them and this one does.",
         "LEMMA AsmDown ==",
         "    /\\ L1!L0!IsFiniteSet(Ids) /\\ \"none\" \\notin Ids",
         "  BY FiniteIds, NoneNotAnId, Zenon",
         "  DEF L1!L0!IsFiniteSet, IsFiniteSet",
         "",
         "\\* Carried once and reused by every level-0 citation below: the refinement",
         "\\* is what lets a level-2 proof reach two INSTANCE hops down.",
         "LEMMA RefinesDown == L1!IndInv => L1!L0!IndInv",
         "  BY Asm, L1!RefinesL0, Zenon",
         ""]
for i in range(LEMMAS):
    lines += lemma(i) + [""]
lines.append("=====================================================================")
with open(OUT, "w") as f:
    f.write("\n".join(lines) + "\n")
print("%s  %d lines, %d lemmas" % (os.path.normpath(OUT), len(lines), LEMMAS))
