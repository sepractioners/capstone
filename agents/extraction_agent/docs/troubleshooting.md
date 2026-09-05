# Known Issues and Lessons Learned

Notes from getting PDF extraction actually working, kept here so the next person (or model) tuning this prompt does not have to rediscover them.

## `any_llm.completion()` Deadlocks Inside the LangGraph Event Loop

`extract_node` in `graph.py` runs inside LangGraph's `ainvoke`, which means it is already executing inside a running asyncio event loop. `any_llm`'s sync `completion()` refuses to run in that situation (`RuntimeError: Cannot use the sync API in an async context`). `extract_page` in `extraction_node.py` must call `any_llm.acompletion()` (awaited), never the sync `completion()`, whenever it is invoked from inside the graph.

## A Local Model Can Return a Technically Valid but Empty Extraction

Testing against a local Ollama model (`gemma4:latest`, 8B, Q4_K_M) with the first version of the system prompt, a plain rules-only list of instructions, produced responses that satisfied the `PageExtraction` schema while leaving every optional field empty, even on pages that plainly contained a title, two named parties, and later a signature block:

```json
{"page_number": 1, "continues_from_previous_page": false}
```

This is not a parsing bug on our side: `response.choices[0].message.parsed` correctly reflected what the model returned. The model was simply not extracting anything.

## Enabling the Model's Thinking Mode Did Not Fix It

`gemma4:latest` advertises a `thinking` capability, and `any_llm`'s Ollama provider forwards `reasoning_effort` straight to Ollama's native `think` parameter. Enabling it (`reasoning_effort="medium"`) produced a detailed, correct reasoning trace, but the final structured answer it committed to was still empty. Thinking mode did not close that gap and added significant latency, so it was not adopted.

## What Actually Fixed It: A Directive Prompt Plus One Worked Example

Rewriting the system prompt in `system_prompt.yaml` to (a) state plainly that leaving a field blank when the information is visibly present is a failure, not caution, (b) give concrete per-field instructions, and (c) include one complete worked example reliably got the model to populate `title`, `parties`, `clauses`, and `key_dates` on real contract text. Verified against a real CUAD document (`Co_Branding Agreement2.pdf`, an amendment naming `PC Quote, Inc.` and `A.B. Watley, Inc.`): the old prompt extracted nothing and the contract stopped at `in_review` for lack of parties; the new prompt correctly extracted the title, both parties, and two clauses, and the contract reached `approved`.

## Remaining Known Limitations With a Small Local Model

- **Run-to-run variance at `temperature=0`.** The same page 1 text produced `key_dates.effective_date = "1996-12-09"` in an isolated single-call test, but came back empty in a full pipeline run of the same file. Local backends do not guarantee the same determinism at `temperature=0` that hosted providers typically do.
- **`contract_type` is rarely populated.** The prompt does not walk the model through classifying a contract type the way it does for title and parties; this is a plausible next prompt iteration rather than a solved problem. `ingest_contract_handler` degrades gracefully with an `unclassified` fallback.
- **Latency.** Each per-page completion call against this local model took roughly 60-95+ seconds on the hardware used for testing. A full batch over the ~31-document CUAD subset would take a long time sequentially. Validate with `run_pipeline.py --limit` first, and prefer a hosted provider when one is available for faster and more consistent extraction.
