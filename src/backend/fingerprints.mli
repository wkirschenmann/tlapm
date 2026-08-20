(* Computing fingerprints of proof obligations.

Copyright (C) 2011  INRIA and Microsoft Corporation
*)

(* tlapm.ml *)
val write_fingerprint:
    Proof.T.obligation -> Proof.T.obligation

val fingerprint_anon:
    Proof.T.obligation -> string
(** The obligation's digest with declared names erased: invariant under
    renaming a `CONSTANT`/`VARIABLE`/`NEW` declaration, where
    [write_fingerprint]'s digest is not.  For the [Fp_classes] probe;
    never used on the normal path, and it does not touch the stored
    fingerprint. *)
