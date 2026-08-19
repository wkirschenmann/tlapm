---------------- MODULE Base ----------------
EXTENDS Naturals
Double(n) == 2 * n
LEMMA BaseLemma == \A n \in Nat : Double(n) = 2 * n
OBVIOUS
==============================================
