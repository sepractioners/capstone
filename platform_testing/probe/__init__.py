"""Subsystem probes — direct-call validators for one agent at a time.

A probe drives a single subsystem (no API, no orchestrator) against a seeded
database, records the full step trace (system prompt + exact context in, raw +
parsed model output out, timing), and scores the deterministic parts against
committed ground truth. Contrast with ``platform_testing.query_bench`` /
``extraction_bench``, which exercise the whole stack through the running API.
"""
