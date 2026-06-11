"""Training infrastructure for the RL / GEPA self-improvement loop.

This package is the *dataset-agnostic* scaffolding that lets TicketGuard iterate
``run -> train -> run -> train`` once a labelled URL dataset arrives. It is built
before the dataset exists by pinning down a stable internal schema and
normalizing whatever shape teammates deliver into it.

Modules:
  * ``dataset`` — canonical ``EvalExample`` schema, a tolerant loader, and a
    deterministic stratified train/val/test split.
  * ``metric`` — the GEPA-compatible scoring function that turns one audit into
    a scalar reward plus natural-language diagnostics (Actionable Side
    Information) for the reflective optimizer.
"""
