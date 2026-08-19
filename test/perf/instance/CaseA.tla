---------------- MODULE CaseA ----------------
EXTENDS Naturals, TLAPS
VARIABLES x, y
I == INSTANCE AA
THEOREM CaseA_thm == I!Init => x = 0
BY DEF I!Init
==============================================
