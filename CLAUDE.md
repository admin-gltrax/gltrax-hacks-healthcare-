# CLAUDE.md: project context for future sessions

Read this first. It is the handoff from the planning and first-build conversation (written Oct 27, 2026). The repo is **public**: keep names, employers and other personal details out of it.

## What this is

**swarm-scheduler**: a patient says what they need ("an in-network cardiologist, nothing before 9am"). An agent places **15 calls at once** to *simulated* medical offices, learns which actually take the plan and have openings, negotiates honestly using real held offers, and **holds** the best slot. The patient approves. A live "directory vs reality" counter shows how wrong provider directories are (the data-asset story). All patients, offices and data are fictional. No real clinic is ever called.

## The competition

Meta Global AI Developer Hackathon (Meta + Cerebral Valley), **startup track**, team of two, theme "Build for Your World".
- Build window Oct 26 to Nov 4, 2026. **Submission due Nov 4, 9:00 PM ET.** Judging Nov 4 to 8, finals Nov 9. (Dates are from third-party summaries; verify against Meta's Official Rules.)
- Startup track is judged on **technical execution and production readiness**, not just a demo.
- Unknown until the Official Rules are read: whether non-Meta text-to-speech is allowed, any healthcare-data or phone-call rules, submission format (video length, repo, demo link), team-size limits.
- Credits: $150 Meta Model API per selected participant (sources disagree on who gets it); partner credits Baseten $100, Modal $100, Fireworks $25.

## Status (honest)

Built and passing: `MOCK_LLM=1 pytest -q` -> 26 tests.
- Meta client, immutable safety block, tool-calling worker, 12 personas + 2 IVR trees, 15-office demo scenario, shared blackboard, 15-way dispatcher, deterministic judge, batch eval CLI, FastAPI + SSE dashboard, token-gated live runs, public replay, Dockerfile, `render.yaml`, CI workflow.

**NOT verified, do not assume:**
- **Nothing has been run against the live Meta API.** All development used `src/mock.py` scripted models, which prove plumbing, not model quality. First job: `python scripts/smoke_meta.py` (every line must say PASS), then run real calls and read transcripts.
- `recordings/demo.jsonl` is a **mock** recording (the UI says so). Replace it with a real-model recording once the prompt is calibrated: `python scripts/make_recording.py`.
- The Docker image was never built here (no daemon); the app was run from a clean runtime-only venv with the same start command instead. `render.yaml` syntax is from memory. The CI workflow may not have been accepted by GitHub (check the Actions tab).
- Cost per call is an unmeasured estimate (about 16 requests per call).

## Meta Model API facts (verified from docs on Oct 27, 2026)

- OpenAI-compatible. Base `https://api.meta.ai/v1`; key in env `MODEL_API_KEY`, **passed explicitly** (the OpenAI SDK does not read it). The old Llama API (`api.llama.com`) was **retired July 6, 2026**: do not use Llama.
- Models: `muse-spark-1.3` (workhorse, $1.25 in / $4.25 out per 1M), `muse-wonder-1.0` (preview, agentic, $4 / $20), `muse-spark-1.2` (use this if you ever send audio to a chat model; 1.3 audio is incomplete), `muse-voice-transcribe-1.0`, `muse-image-1.0`, `sam-3.1`. Open weights: Muse Spark Open (816B MoE, 42B active) via Fireworks (`accounts/fireworks/models/muse-spark-open`) or Baseten (`meta-models/muse-spark-open`). `-contributor` variants are cheap but **Meta trains on your prompts** and cap at 100 RPM: simulated data only, never real PHI.
- Rate limits are per team: 3,000 RPM / 4M TPM for Spark and Wonder.
- **Tool calling gotchas:** `tool_choice` supports only `"auto"` (never send it; handle replies with and without tool calls). On Chat Completions, tools nest under `function`, and the **full assistant message including `tool_calls` must be echoed back** before the `tool` messages (omitting it is a 400). Function names must match `^[a-zA-Z0-9_.-]+$`. Tool arguments are not guaranteed valid: validate. `reasoning_effort` accepts minimal/low/medium/high/xhigh (never `none`).
- **No text-to-speech and no speech-to-speech.** Meta has realtime speech-to-text only: `wss://api.meta.ai/v1/asr/realtime`, auth in a first JSON handshake frame (`{"authorization":{"accessToken":"Bearer <key>"},"audioEncoding":"PCM_24KHZ","model":"muse-voice-transcribe-1.0","mode":"PUSH_TO_TALK"}`), binary PCM16 mono 24kHz frames, `{"type":"endStream"}` to finish, `$0.18/hr`, 256 concurrent streams. 8kHz mu-law (telephony) is unconfirmed. A voice layer needs a non-Meta TTS (check the rules).
- Docs: https://dev.meta.ai/docs (models, tool-calling, speech-to-text, computer-use, pricing-rate-limits, muse-spark-open/deploy).

## Where things are

See README.md for the layout. Key files: `src/llm.py` (client; `get_llm(role)`), `src/config.py` (per-role models), `src/safety.py` (safety block + checks), `src/agents/worker.py` (the call agent and its tools), `src/sim/` (personas, IVR, scenarios, office), `src/swarm/` (blackboard, events, dispatcher), `src/eval/` (judge, batch CLI), `src/api/` (server + dashboard), `prompts/worker_v0.txt` (the only prompt the improvement loop may edit), `DEPLOY.md` (hosting).

## Invariants: do not break these

1. **`SAFETY_BLOCK` in `src/safety.py` is immutable** to any self-improvement loop; assert `SAFETY_SHA` is unchanged. Safety pass rate must stay 100% across iterations.
2. **The worker has no tool that books or confirms.** It can only record facts/offers, hold, read the blackboard, press keys, hand off, end. Only the patient confirms. A test enforces this.
3. **Data minimization by construction:** the worker is only ever given name, DOB, member ID, plan, visit reason, constraints. Never add more.
4. **Honest leverage only:** workers may mention other offices' held *times* returned by `check_blackboard`, never office names, never invented offers. The judge fails fabricated leverage.
5. **Never tune on the `holdout` split** (`OfficeScenario.split`). Report baseline vs improved on holdout.
6. **Live runs need `APP_ACCESS_TOKEN`**; the replay is public and free. Run **exactly one instance** (state is in memory). Never commit `.env`. Never put real PHI through the contributor models.
7. Simulated offices are always labeled as simulated in the UI.

## Roadmap (cut order if behind: computer-use booking, multilingual, voice tiles, cost reasoning; protect the swarm, honest leverage, truth counter, eval chart, production checklist)

- **Oct 28:** run `smoke_meta.py`; 20 live scenarios; read transcripts; calibrate worker prompt and personas; first real 15-call swarm.
- **Oct 29:** honest negotiation verified in a real run; intake via Wonder structured output (`src/intake.py` exists); insurance-card photo via Muse Spark vision (fake card).
- **Oct 30:** 150-200-call evals using open-weight Muse Spark Open as the receptionists; LLM-judge quality (`llm_quality` exists); **record baseline v0**; SQLite run store; per-call cost and latency.
- **Oct 31:** self-improvement loop: Wonder critic clusters failures, proposes patches to `prompts/worker_v0.txt`; accept only if holdout success rises and safety stays 100%; chart v0 to v3.
- **Nov 1:** voice layer on 3 featured tiles: TTS -> Muse Voice Transcribe realtime -> worker.
- **Nov 2:** polish; real-model recording; Docker/CI green; backup demo video.
- **Nov 3:** freeze, rehearse, **submit tonight**. Nov 4 is buffer only.

## Production-readiness checklist (startup-track scoring)

Done: per-call error isolation, client retries/timeouts, dev/holdout split, safety hash, token-gated live runs, cost guards, health check, audit log per run, non-root single-process Dockerfile, CI workflow, replay mode.
Still to build: global swarm deadline, `CallChannel` telephony adapter interface (simulated + Twilio-shaped stub), SQLite run store, PHI-safe log redaction, cost/latency metrics, `docs/COMPLIANCE.md` (design compatible with HIPAA; do not claim compliance), pilot-path slide.

## History and decisions (why things are the way they are)

- Started from a question about a voice agent calling insurers for benefits; moved to patient-facing appointment finding; chose the 15-way swarm because it is the most demonstrable "frontier" behavior.
- Eligibility (271) and payer FHIR APIs were explored earlier; a separate Node Blue Button sandbox starter exists outside this repo and is not part of the build.
- Earlier docs in `docs/` mention Llama, Pipecat and Twilio; they carry a banner saying the stack is now the Meta Model API. Twilio/real telephony only matters for a post-hackathon pilot.
- A private planning document (team split, detailed schedule) is intentionally not in this public repo.
