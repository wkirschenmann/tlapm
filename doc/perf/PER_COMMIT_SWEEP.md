# Per-commit measurement sweep, `tlapm-performance-upstream-proposal`

One binary per commit, built from that commit alone, measured on five corpora.

  * `gen` is `tlapm -N --nofp` — parse, elaborate, generate obligations, stop.
  * `prep` is `tlapm --noproving --nofp` — the whole per-obligation pipeline with
    no prover launched, so the figure is prover-independent.
  * `peak` is the maximum resident set of the `prep` run, from `/usr/bin/time -f %M`.

One run per cell, each taken immediately after that commit's own build.  `> 900 s`
means the run was stopped at the fifteen-minute ceiling; `aborted` means it hit the
12 GB address-space cap the runs are made under (`ulimit -v 12000000`), and there
the peak *is* the failure.  `main` appears twice, as `c00` at the start of the
campaign and `c00b` at the end, which is the drift the campaign carries.

The whole campaign is **one boot of one container** — absolute values are not
comparable across restarts, so every row in the raw CSV is stamped with the boot
it was measured on, and this table contains rows from boot `1787343239` only.

Machine: Intel Xeon @ 2.80 GHz, 4 cores, 16 GB, Linux 6.18.44, OCaml 5.1.0 switch.

Three corpora are the public synthetic family, reproducible from the generator.
Two are private specifications: only these aggregate figures are published, and no
specification content appears here or anywhere in the repository.


> **This campaign is still running.**  `prep` and `peak` cells shown as
> `—` have not been measured yet; nothing here is filled in from another
> boot or from an earlier campaign.  Outstanding:
>
> * ffi: c01, c02, c03, c04, c05, c08, c10, c11
> * mono: c01, c02, c03, c04, c05, c06, c08, c10, c11


## public synthetic, 1 800 obligations

| point | commit | gen | prep | peak |
|---|---|---:|---:|---:|
| c00 | `main` base of the branch (tlaplus/tlapm master) | 2.59 s | 51.7 s | 1.72 GB |
| c01 | `445c619` util/timing: make clock accounting nestable | 2.07 s | 50.4 s | 1.72 GB |
| c02 | `e71feaf` util/timing: host the named pipeline clocks | 2.12 s | 51.8 s | 1.72 GB |
| c03 | `023f200` timing: attribute generation, fingerprinting and fp saving to their clocks | 2.20 s | 50.5 s | 1.72 GB |
| c04 | `4901a02` backend/schedule: reap finished provers early; refresh deadline clock | 2.18 s | 49.7 s | 1.72 GB |
| c05 | `a0ed498` fix: kill timed-out provers with SIGTERM, not SIGHUP | 2.12 s | 50.9 s | 1.72 GB |
| c06 | `cb9ce43` util/Deque: cheaper nth, first_n and equal on rear-heavy deques | 329 ms | 45.0 s | 1.74 GB |
| c07 | `0e47a7e` backend/prep: expand visible definitions in a single pass | 335 ms | 30.4 s | 1.42 GB |
| c08 | `dc37462` backend/prep: prune hidden definitions unreachable from the goal | 338 ms | 29.4 s | 1.42 GB |
| c09 | `be2cb6b` backend/prep: prune unreferenced hidden facts from obligation contexts | 341 ms | 8.95 s | 168 MB |
| c10 | `0a00f77` backend/prep: reuse preparation work across obligations sharing a context prefix | 319 ms | 6.38 s | 167 MB |
| c11 | `a5158d1` backend/prep: prefix-resume cache for Elab.normalize | 345 ms | 6.64 s | 166 MB |
| c12 | `991239f` backend/prep: differential oracle for the normalize cache | 331 ms | 6.39 s | 167 MB |
| c13 | `b70585f` backend/schedule: pull tasks from a stream instead of a materialized list | 320 ms | 7.14 s | 154 MB |
| c14 | `ba1df8c` module/Elab: make ENABLED-axioms detection linear in context size | 260 ms | 6.42 s | 156 MB |
| c15 | `809b30e` expr/Levels: resolve de Bruijn reference levels without slicing the context | 249 ms | 6.67 s | 156 MB |
| c16 | `393164e` backend/toolbox: single-pass definition expansion in the result printer | 249 ms | 6.37 s | 156 MB |
| c17 | `690a261` expr/parser: memoize the two instances of each grammar rule | 237 ms | 6.55 s | 154 MB |
| c18 | `9a08f81` util/property: monomorphic pid equality, loop-based lookups | 227 ms | 6.29 s | 156 MB |
| c19 | `4e3ec9f` lsp: replace the per-step RangeMap.partition by a sorted obligation pool | 247 ms | 6.23 s | 155 MB |
| c20 | `fba0670` Ctx: logarithmic index lookup | 233 ms | 5.96 s | 155 MB |
| c21 | `3525625` backend/Smtlib: compile identifier-escaping regexes once | 234 ms | 6.38 s | 155 MB |
| c22 | `16becd8` expr/Subst: walk substitution spines in app_ix without allocating | 245 ms | 6.44 s | 155 MB |
| c23 | `abf13ea` backend+encode: skip identity rebuilds when flattening extracts nothing | 255 ms | 5.89 s | 155 MB |
| c24 | `1d1b05a` backend/prep: emit obligation comments into solver files only when kept | 230 ms | 5.88 s | 155 MB |
| c25 | `2c2b318` expr/Levels: stop the level cache pinning one context per obligation | 223 ms | 5.97 s | 76 MB |
| c26 | `bd0ecd1` expr/Constness: constant-time De Bruijn resolution in add_constness | 240 ms | 5.57 s | 76 MB |
| c00b | `main` re-measured at the end of the campaign (drift check) | 2.15 s | 50.4 s | 1.72 GB |

## public synthetic, 600 obligations

| point | commit | gen | prep | peak |
|---|---|---:|---:|---:|
| c00 | `main` base of the branch (tlaplus/tlapm master) | 405 ms | 4.30 s | 232 MB |
| c01 | `445c619` util/timing: make clock accounting nestable | 241 ms | 3.41 s | 232 MB |
| c02 | `e71feaf` util/timing: host the named pipeline clocks | 222 ms | 3.63 s | 232 MB |
| c03 | `023f200` timing: attribute generation, fingerprinting and fp saving to their clocks | 228 ms | 3.65 s | 232 MB |
| c04 | `4901a02` backend/schedule: reap finished provers early; refresh deadline clock | 213 ms | 3.35 s | 232 MB |
| c05 | `a0ed498` fix: kill timed-out provers with SIGTERM, not SIGHUP | 218 ms | 3.33 s | 232 MB |
| c06 | `cb9ce43` util/Deque: cheaper nth, first_n and equal on rear-heavy deques | 132 ms | 2.87 s | 224 MB |
| c07 | `0e47a7e` backend/prep: expand visible definitions in a single pass | 133 ms | 2.75 s | 215 MB |
| c08 | `dc37462` backend/prep: prune hidden definitions unreachable from the goal | 138 ms | 2.76 s | 204 MB |
| c09 | `be2cb6b` backend/prep: prune unreferenced hidden facts from obligation contexts | 134 ms | 936 ms | 61 MB |
| c10 | `0a00f77` backend/prep: reuse preparation work across obligations sharing a context prefix | 138 ms | 828 ms | 60 MB |
| c11 | `a5158d1` backend/prep: prefix-resume cache for Elab.normalize | 136 ms | 830 ms | 59 MB |
| c12 | `991239f` backend/prep: differential oracle for the normalize cache | 137 ms | 813 ms | 59 MB |
| c13 | `b70585f` backend/schedule: pull tasks from a stream instead of a materialized list | 140 ms | 809 ms | 57 MB |
| c14 | `ba1df8c` module/Elab: make ENABLED-axioms detection linear in context size | 134 ms | 788 ms | 57 MB |
| c15 | `809b30e` expr/Levels: resolve de Bruijn reference levels without slicing the context | 134 ms | 780 ms | 57 MB |
| c16 | `393164e` backend/toolbox: single-pass definition expansion in the result printer | 127 ms | 779 ms | 57 MB |
| c17 | `690a261` expr/parser: memoize the two instances of each grammar rule | 127 ms | 800 ms | 57 MB |
| c18 | `9a08f81` util/property: monomorphic pid equality, loop-based lookups | 123 ms | 738 ms | 57 MB |
| c19 | `4e3ec9f` lsp: replace the per-step RangeMap.partition by a sorted obligation pool | 125 ms | 723 ms | 58 MB |
| c20 | `fba0670` Ctx: logarithmic index lookup | 134 ms | 704 ms | 57 MB |
| c21 | `3525625` backend/Smtlib: compile identifier-escaping regexes once | 123 ms | 704 ms | 58 MB |
| c22 | `16becd8` expr/Subst: walk substitution spines in app_ix without allocating | 122 ms | 723 ms | 58 MB |
| c23 | `abf13ea` backend+encode: skip identity rebuilds when flattening extracts nothing | 121 ms | 691 ms | 58 MB |
| c24 | `1d1b05a` backend/prep: emit obligation comments into solver files only when kept | 129 ms | 701 ms | 58 MB |
| c25 | `2c2b318` expr/Levels: stop the level cache pinning one context per obligation | 121 ms | 711 ms | 36 MB |
| c26 | `bd0ecd1` expr/Constness: constant-time De Bruijn resolution in add_constness | 124 ms | 692 ms | 36 MB |
| c00b | `main` re-measured at the end of the campaign (drift check) | 237 ms | 3.58 s | 232 MB |

## public synthetic, 71 obligations

| point | commit | gen | prep | peak |
|---|---|---:|---:|---:|
| c00 | `main` base of the branch (tlaplus/tlapm master) | 155 ms | 129 ms | 21 MB |
| c01 | `445c619` util/timing: make clock accounting nestable | 89 ms | 105 ms | 21 MB |
| c02 | `e71feaf` util/timing: host the named pipeline clocks | 89 ms | 113 ms | 21 MB |
| c03 | `023f200` timing: attribute generation, fingerprinting and fp saving to their clocks | 86 ms | 114 ms | 21 MB |
| c04 | `4901a02` backend/schedule: reap finished provers early; refresh deadline clock | 91 ms | 109 ms | 21 MB |
| c05 | `a0ed498` fix: kill timed-out provers with SIGTERM, not SIGHUP | 91 ms | 146 ms | 21 MB |
| c06 | `cb9ce43` util/Deque: cheaper nth, first_n and equal on rear-heavy deques | 86 ms | 103 ms | 21 MB |
| c07 | `0e47a7e` backend/prep: expand visible definitions in a single pass | 82 ms | 105 ms | 21 MB |
| c08 | `dc37462` backend/prep: prune hidden definitions unreachable from the goal | 86 ms | 105 ms | 21 MB |
| c09 | `be2cb6b` backend/prep: prune unreferenced hidden facts from obligation contexts | 84 ms | 101 ms | 21 MB |
| c10 | `0a00f77` backend/prep: reuse preparation work across obligations sharing a context prefix | 91 ms | 113 ms | 21 MB |
| c11 | `a5158d1` backend/prep: prefix-resume cache for Elab.normalize | 85 ms | 108 ms | 21 MB |
| c12 | `991239f` backend/prep: differential oracle for the normalize cache | 87 ms | 104 ms | 21 MB |
| c13 | `b70585f` backend/schedule: pull tasks from a stream instead of a materialized list | 95 ms | 106 ms | 21 MB |
| c14 | `ba1df8c` module/Elab: make ENABLED-axioms detection linear in context size | 90 ms | 112 ms | 21 MB |
| c15 | `809b30e` expr/Levels: resolve de Bruijn reference levels without slicing the context | 84 ms | 103 ms | 21 MB |
| c16 | `393164e` backend/toolbox: single-pass definition expansion in the result printer | 84 ms | 102 ms | 21 MB |
| c17 | `690a261` expr/parser: memoize the two instances of each grammar rule | 89 ms | 107 ms | 21 MB |
| c18 | `9a08f81` util/property: monomorphic pid equality, loop-based lookups | 91 ms | 113 ms | 21 MB |
| c19 | `4e3ec9f` lsp: replace the per-step RangeMap.partition by a sorted obligation pool | 90 ms | 110 ms | 21 MB |
| c20 | `fba0670` Ctx: logarithmic index lookup | 85 ms | 101 ms | 21 MB |
| c21 | `3525625` backend/Smtlib: compile identifier-escaping regexes once | 90 ms | 108 ms | 21 MB |
| c22 | `16becd8` expr/Subst: walk substitution spines in app_ix without allocating | 92 ms | 115 ms | 21 MB |
| c23 | `abf13ea` backend+encode: skip identity rebuilds when flattening extracts nothing | 84 ms | 105 ms | 21 MB |
| c24 | `1d1b05a` backend/prep: emit obligation comments into solver files only when kept | 83 ms | 105 ms | 21 MB |
| c25 | `2c2b318` expr/Levels: stop the level cache pinning one context per obligation | 86 ms | 102 ms | 21 MB |
| c26 | `bd0ecd1` expr/Constness: constant-time De Bruijn resolution in add_constness | 93 ms | 110 ms | 21 MB |
| c00b | `main` re-measured at the end of the campaign (drift check) | 93 ms | 110 ms | 21 MB |

## private refinement chain, 9 967 obligations

| point | commit | gen | prep | peak |
|---|---|---:|---:|---:|
| c00 | `main` base of the branch (tlaplus/tlapm master) | 33.9 s | — | — |
| c01 | `445c619` util/timing: make clock accounting nestable | 32.5 s | — | — |
| c02 | `e71feaf` util/timing: host the named pipeline clocks | 32.9 s | — | — |
| c03 | `023f200` timing: attribute generation, fingerprinting and fp saving to their clocks | 33.4 s | — | — |
| c04 | `4901a02` backend/schedule: reap finished provers early; refresh deadline clock | 32.0 s | — | — |
| c05 | `a0ed498` fix: kill timed-out provers with SIGTERM, not SIGHUP | 34.8 s | — | — |
| c06 | `cb9ce43` util/Deque: cheaper nth, first_n and equal on rear-heavy deques | 3.91 s | > 900 s | — |
| c07 | `0e47a7e` backend/prep: expand visible definitions in a single pass | 3.72 s | aborted | 11.19 GB |
| c08 | `dc37462` backend/prep: prune hidden definitions unreachable from the goal | 3.71 s | — | — |
| c09 | `be2cb6b` backend/prep: prune unreferenced hidden facts from obligation contexts | 3.95 s | 764.5 s | 4.88 GB |
| c10 | `0a00f77` backend/prep: reuse preparation work across obligations sharing a context prefix | 3.80 s | — | — |
| c11 | `a5158d1` backend/prep: prefix-resume cache for Elab.normalize | 3.81 s | — | — |
| c12 | `991239f` backend/prep: differential oracle for the normalize cache | 3.93 s | 177.8 s | 4.17 GB |
| c13 | `b70585f` backend/schedule: pull tasks from a stream instead of a materialized list | 3.85 s | 179.9 s | 4.00 GB |
| c14 | `ba1df8c` module/Elab: make ENABLED-axioms detection linear in context size | 2.46 s | 177.7 s | 3.94 GB |
| c15 | `809b30e` expr/Levels: resolve de Bruijn reference levels without slicing the context | 2.35 s | 175.4 s | 3.94 GB |
| c16 | `393164e` backend/toolbox: single-pass definition expansion in the result printer | 2.30 s | 176.9 s | 3.94 GB |
| c17 | `690a261` expr/parser: memoize the two instances of each grammar rule | 1.79 s | 179.4 s | 3.93 GB |
| c18 | `9a08f81` util/property: monomorphic pid equality, loop-based lookups | 1.72 s | 170.0 s | 3.91 GB |
| c19 | `4e3ec9f` lsp: replace the per-step RangeMap.partition by a sorted obligation pool | 1.73 s | 172.3 s | 3.91 GB |
| c20 | `fba0670` Ctx: logarithmic index lookup | 1.77 s | 178.5 s | 3.91 GB |
| c21 | `3525625` backend/Smtlib: compile identifier-escaping regexes once | 1.70 s | 168.7 s | 3.92 GB |
| c22 | `16becd8` expr/Subst: walk substitution spines in app_ix without allocating | 1.65 s | 173.9 s | 4.00 GB |
| c23 | `abf13ea` backend+encode: skip identity rebuilds when flattening extracts nothing | 1.77 s | 174.4 s | 4.00 GB |
| c24 | `1d1b05a` backend/prep: emit obligation comments into solver files only when kept | 1.66 s | 173.2 s | 4.00 GB |
| c25 | `2c2b318` expr/Levels: stop the level cache pinning one context per obligation | 1.76 s | 144.8 s | 400 MB |
| c26 | `bd0ecd1` expr/Constness: constant-time De Bruijn resolution in add_constness | 1.69 s | 146.4 s | 407 MB |
| c00b | `main` re-measured at the end of the campaign (drift check) | 33.8 s | > 900 s | — |

## private 30k monolith, 29 965 obligations

| point | commit | gen | prep | peak |
|---|---|---:|---:|---:|
| c00 | `main` base of the branch (tlaplus/tlapm master) | 63.4 s | — | — |
| c01 | `445c619` util/timing: make clock accounting nestable | 62.9 s | — | — |
| c02 | `e71feaf` util/timing: host the named pipeline clocks | 62.2 s | — | — |
| c03 | `023f200` timing: attribute generation, fingerprinting and fp saving to their clocks | 62.3 s | — | — |
| c04 | `4901a02` backend/schedule: reap finished provers early; refresh deadline clock | 62.5 s | — | — |
| c05 | `a0ed498` fix: kill timed-out provers with SIGTERM, not SIGHUP | 65.7 s | — | — |
| c06 | `cb9ce43` util/Deque: cheaper nth, first_n and equal on rear-heavy deques | 9.93 s | — | — |
| c07 | `0e47a7e` backend/prep: expand visible definitions in a single pass | 9.96 s | aborted | 11.19 GB |
| c08 | `dc37462` backend/prep: prune hidden definitions unreachable from the goal | 11.5 s | — | — |
| c09 | `be2cb6b` backend/prep: prune unreferenced hidden facts from obligation contexts | 10.3 s | > 900 s | — |
| c10 | `0a00f77` backend/prep: reuse preparation work across obligations sharing a context prefix | 10.6 s | — | — |
| c11 | `a5158d1` backend/prep: prefix-resume cache for Elab.normalize | 10.5 s | — | — |
| c12 | `991239f` backend/prep: differential oracle for the normalize cache | 10.5 s | aborted | 11.19 GB |
| c13 | `b70585f` backend/schedule: pull tasks from a stream instead of a materialized list | 10.3 s | 405.7 s | 11.10 GB |
| c14 | `ba1df8c` module/Elab: make ENABLED-axioms detection linear in context size | 6.69 s | 389.9 s | 10.93 GB |
| c15 | `809b30e` expr/Levels: resolve de Bruijn reference levels without slicing the context | 7.36 s | 397.6 s | 10.94 GB |
| c16 | `393164e` backend/toolbox: single-pass definition expansion in the result printer | 6.16 s | 395.2 s | 10.94 GB |
| c17 | `690a261` expr/parser: memoize the two instances of each grammar rule | 4.31 s | 395.7 s | 10.94 GB |
| c18 | `9a08f81` util/property: monomorphic pid equality, loop-based lookups | 4.69 s | 366.7 s | 10.79 GB |
| c19 | `4e3ec9f` lsp: replace the per-step RangeMap.partition by a sorted obligation pool | 4.37 s | 377.6 s | 10.79 GB |
| c20 | `fba0670` Ctx: logarithmic index lookup | 4.27 s | 379.3 s | 10.80 GB |
| c21 | `3525625` backend/Smtlib: compile identifier-escaping regexes once | 4.38 s | 362.5 s | 10.81 GB |
| c22 | `16becd8` expr/Subst: walk substitution spines in app_ix without allocating | 4.22 s | 364.9 s | 10.86 GB |
| c23 | `abf13ea` backend+encode: skip identity rebuilds when flattening extracts nothing | 4.19 s | 365.2 s | 10.86 GB |
| c24 | `1d1b05a` backend/prep: emit obligation comments into solver files only when kept | 4.25 s | 377.4 s | 10.86 GB |
| c25 | `2c2b318` expr/Levels: stop the level cache pinning one context per obligation | 4.21 s | 288.0 s | 1.08 GB |
| c26 | `bd0ecd1` expr/Constness: constant-time De Bruijn resolution in add_constness | 4.35 s | 283.1 s | 1.09 GB |
| c00b | `main` re-measured at the end of the campaign (drift check) | 65.0 s | aborted | 11.19 GB |
