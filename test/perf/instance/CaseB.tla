---------------- MODULE CaseB ----------------
EXTENDS Naturals, FiniteSets, TLAPS
CONSTANTS Instances
VARIABLES x, y
vars == <<x, y>>
A(i) == INSTANCE AA WITH x <- x[i], y <- y[i]
Init == \A i \in Instances : A(i)!Init
THEOREM CaseB_thm == Init => \A i \in Instances : x[i] = 0
BY DEF Init, A!Init
==============================================
