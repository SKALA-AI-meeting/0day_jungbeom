"""Harness: the code around the model (capstone PDF ch.6). The model only proposes the next reply or tool;
execution, limits, records and recovery are done here.

  Instructions  instructions.py  prompts/*.md, versioned, never inlined in code
  Tools         tools.py         MCP clients, result truncation, errors returned to the model as text
  Context       context.py       token budget for the transcript, RAG results injected as tool messages
  State·Memory  memory.py        LangGraph checkpointer (PostgreSQL), thread id per task, resume after approval
  Agent Loop    loop.py          max 8 graph steps, 120 s per task, same tool at most 3 times
  Guardrails    guardrails.py    change tools that need approval stop at interrupt(), PII masking, output guard
  Recovery      recovery.py      429/5xx retried twice, then fallback model, then FAILED
  Observability observability.py one trace id per task: nodes, tools, tokens, latency; LangSmith if configured
"""
