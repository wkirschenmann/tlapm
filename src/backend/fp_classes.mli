(* Probe: obligations identical up to renaming declared names.

   Enabled by the TLAPM_FP_CLASSES environment variable; inert otherwise.
   See the implementation for what a class means and how it is audited. *)

val enabled: bool

val record: Proof.T.obligation -> unit
(** Record a fingerprinted obligation (called once per obligation, right
    after its fingerprint is computed). *)

val record_shipped: Proof.T.obligation -> unit
(** Record the form actually handed to the backends, which is the one the
    audit compares. *)

val report: unit -> unit
(** Print the classes and their audit verdict at the end of a run. *)
