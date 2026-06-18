# Architecture

`mcp-govcheck` is a small, layered Python package. The design goal is that the
**core is pure and testable** (no MCP dependency, no I/O, no clocks) and only a
single thin adapter touches the `mcp` SDK or the filesystem. That keeps the
governance logic verifiable in isolation and makes the safety properties (see
`evals/safety_cases.py`) meaningful.

## Layers

```
                 cli.py                 ← argparse; scan/attest; exit codes 0/1/2; UTF-8 stdio
                   │
        ┌──────────┴───────────┐
     scan path              attest path
        │                       │
  introspect.py            evidence.py        ← evidence.load_calls() parses JSONL log
  (ONLY file that           (pure)
   imports `mcp`)              │
        │                       │
   ToolSpec[]              ToolCall[]
        │                       │
   rubric.py ──► Finding[]  evidence.attest() ──► EvidencePack
        │                       │
   score.py ──► Scorecard       │
        └──────────┬────────────┘
               report.py        ← markdown + deterministic JSON
                   │
              controls.py       ← canonical ISO 27001 / SOC 2 catalog (single source of truth)
                   │
                types.py        ← dataclasses + enums (no deps)
```

## Modules

- **`types.py`** — all shared data: `ToolSpec`, `ToolCall`, `Finding`, `Scorecard`,
  `ControlEvidence`, `EvidencePack`, and the `Severity` / `CheckResult` / `EvidenceStatus`
  enums. Pure data; everything else passes these around.
- **`controls.py`** — the canonical control catalog. Every control id (`ISO27001:A.8.2`,
  `SOC2:CC6.1`, …) is defined here once and imported everywhere; nothing else hard-codes a
  control id or title. `validate_refs()` is what makes rubric/policy loading fail loud on a
  dangling reference.
- **`rubric.py`** — declarative checks. A `Check` selects tools by glob and applies one of a
  small **rule vocabulary** (`confirmation_required`, `forbidden_param`, `description_required`,
  `params_documented`) to produce a `Finding`. Rubrics are validated on load (unknown rule,
  unknown control, duplicate id, empty rubric all raise).
- **`score.py`** — aggregates `Finding[]` into a `Scorecard` with pass-rate (ignoring
  not-applicable), severity breakdown, and the set of implicated controls.
- **`evidence.py`** — the `attest` half. `load_calls()` parses a JSONL log into `ToolCall`s
  (tolerant of field-name variants; fails loud on malformed JSON). `attest()` evaluates
  control-mapped `EvidencePolicy` objects: a control is only `SATISFIED` with ≥1 supporting and
  0 violating calls; a single violation flips it to `VIOLATED` and records the offending calls
  as exceptions — evidence is never silently dropped.
- **`introspect.py`** — the only SDK-coupled module. `tools_from_schema()` parses a static JSON
  file; `tools_from_server()` launches a stdio MCP server, runs the client handshake, and calls
  `list_tools()`. A tool's JSON-Schema `inputSchema.properties` maps to `ToolSpec.params`.
- **`report.py`** — markdown + JSON renderers. JSON is `sort_keys=True` so output is
  deterministic and snapshot-friendly.
- **`cli.py`** — the two subcommands, the exit-code contract (0 clean / 1 findings / 2 error),
  and a UTF-8 stdio shim (the report glyphs ✅/❌ crash the default Windows console codec).

## Data flow

**scan:** `MCP server | schema.json → introspect → ToolSpec[] → rubric.evaluate → Finding[] →
score → Scorecard → report → markdown/JSON`

**attest:** `log.jsonl → load_calls → ToolCall[] → attest(policies) → EvidencePack → report →
markdown/JSON`

## Why static / design-time

A runtime gateway (proxy) is the obvious place to enforce policy, and that space is well served.
But enforcement and **evidence** are different jobs. An auditor doesn't want to be in the request
path — they want to inspect the *design* of the capability surface and the *record* of its use.
`mcp-govcheck` is built for that second job, which is why it never executes a tool and never
holds a connection open. The trade-off: it cannot *prevent* a bad call in real time (a gateway's
job), only *evaluate the design* and *attest to the record*.

## Provenance

The patterns here are generalized from private operational hooks (a real allow/deny gate, a
write-verify ledger with a pass/fail summary, and ISO 27001 / SOC 2 control mappings) into clean,
tested, reusable infrastructure. The eval discipline (labeled fixtures + a timestamped, append-only
`BENCHMARK.md`) follows the same convention used in the author's `wikilens` project.

## Testing

- `tests/` — unit tests per module (controls, rubric, score, evidence, report, introspect, cli).
  The live-server introspection path is exercised by the CLI smoke against the demo server rather
  than a mocked subprocess handshake.
- `evals/` — labeled scan-accuracy scenarios (`scenarios.yaml` over `fixtures/`) plus adversarial
  safety properties (`safety_cases.py`). `run_evals.py` gates on safety and appends to `BENCHMARK.md`.
