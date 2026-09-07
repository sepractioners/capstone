"""Orchestrator agent: turn one user message into a bounded execution plan.

The orchestrator (planner) receives a free-form user message and decides whether to:
- Extract (if file attached): pull a contract into the system
- Analyze: answer a question over stored contracts
- Clarify: if the message is not actionable

It produces a minimal ordered sequence of steps (up to PLANNER_MAX_STEPS),
threads step outputs into following steps, and applies deterministic guardrails.
"""
