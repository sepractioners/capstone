"""LangGraph extraction agent: reads a PDF/JSON/CSV contract file, uses an
LLM (via any-llm) to pull structured fields out of PDFs, merges results
itself, and calls the CLM MCP server's `ingest_contract` tool to persist
what it found. See pipeline.py for the single entry point.
"""
