# swarm-scheduler

An agent that calls many (simulated) medical offices at once to find an in-network appointment, built on the Meta Model API for the Meta Global AI Developer Hackathon.

All offices, patients and data are fictional. No real clinic is ever called.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Offline, no key needed (scripted models: exercises the plumbing, not model quality)
MOCK_LLM=1 pytest -q
MOCK_LLM=1 uvicorn src.api.server:app --port 8000      # open http://localhost:8000 and click Start live swarm

# With the real Meta Model API
cp .env.example .env        # add MODEL_API_KEY
python scripts/smoke_meta.py                            # every line should say PASS
uvicorn src.api.server:app --port 8000
```

Add `?debug=1` to the dashboard URL to show each office's hidden persona.

**Voice intake:** click **🎙 Speak**, say the request, click **Stop**. The browser converts the recording to 16 kHz WAV and the server transcribes it with Muse Voice Transcribe (`POST /v1/asr/transcribe`, see `src/voice.py`); the text lands in the request box for review before you start. Browsers only allow the mic on `localhost` or HTTPS, and it uses the same access token as live runs.

## Hosting

Runs as one Docker container (`Dockerfile`, `render.yaml`). Visitors can watch a free recorded replay; live runs need an access token so nobody can spend your model credits. See [DEPLOY.md](DEPLOY.md).

## Evals

```bash
python -m src.eval.run_batch --n 40 --split dev --k 8   # isolated calls, scored against ground truth
python -m src.eval.run_batch --swarm                    # the fixed 15-office demo, shared blackboard
```

Results land in `data/runs/` with the prompt hash and the safety-block hash. Keep the `holdout` split out of prompt tuning.

## Layout

| Path | Purpose |
|---|---|
| `src/llm.py`, `src/config.py` | Meta Model API client (OpenAI-compatible) and per-role models |
| `src/safety.py` | Immutable safety block, data-minimization and honesty checks |
| `src/agents/worker.py` | The call agent and its tools (no tool can confirm a booking) |
| `src/sim/` | Personas, IVR trees, scenario generator, simulated office |
| `src/swarm/` | Blackboard, event bus, 15-way dispatcher |
| `src/eval/` | Deterministic judge, optional LLM quality judge, batch CLI |
| `src/api/` | FastAPI server, SSE stream, dashboard |
| `src/directory/` | Real provider data: NPPES connector (`data/directory/` holds the Phoenix cardiology snapshot); see `docs/provider-data.md` |
| `src/intake.py`, `src/voice.py` | Patient request: speech to text (Muse Voice Transcribe), text to constraints |
| `prompts/worker_v0.txt` | The tunable worker prompt (the self-improvement loop edits this, never the safety block) |
| `src/mock.py` | Offline scripted models for development |

## Per-role models

Set in `.env`. Defaults: Spark 1.3 for the worker, judge and receptionists; Wonder for planner and critic. To run receptionists on open-weight Muse Spark via a partner host, see the commented block in `.env.example`.

## Status

`scripts/smoke_meta.py` passes all checks against the live Meta Model API (2026-10-27): auth, the model IDs for every role (`muse-spark-1.3`, `muse-wonder-1.0`), plain chat, tool calls, and structured output. The full swarm has not yet been run end to end on the live API.
