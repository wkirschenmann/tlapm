---------------- MODULE AA ----------------
EXTENDS Naturals
VARIABLES x, y
Init == x = 0 /\ y = "idle"
Next == x' = x + 1 /\ y' = y
============================================
