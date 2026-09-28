# Evaluation harness

`questions.json` pairs a question with an *expectation*, not a hardcoded
answer string, since the whole point of the app is that it works on a CSV
it has never seen:

- `exact_value`: a single scalar the SQL should reproduce exactly
  (row counts, distinct counts -- things we can compute independently
  with pandas/duckdb as ground truth in the runner itself).
- `answerable`: the model should produce a working query and get rows
  back; we don't assert the exact number since the point is "does the
  pipeline work end to end," not "does the LLM always pick identical SQL."
- `refusal`: the question is intentionally out of scope for the schema
  (no shoe-size column, no cost/profit column) -- the model should say
  so rather than invent an answer. This is the guardrail check.

Run:

```bash
python eval/run_eval.py
```

Requires the API server running locally (default http://localhost:8000)
and a working LLM backend (Ollama pulled + serving, or an OpenAI-compatible
endpoint configured in .env).
