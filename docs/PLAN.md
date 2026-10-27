# Swarm Scheduler: Locked Plan for the Meta Global AI Developer Hackathon

> **Direction changed Oct 27, 2026.** The product is now **PJ Health**, a patient-first dashboard ("healthcare built for the patient, not the doctor"). The swarm described here is now one capability PJ uses to schedule. The current framework, status and priorities are in the [README](../README.md) and [CLAUDE.md](../CLAUDE.md). This plan is still valid for the swarm itself.

Written Tue Oct 27, 2026. Sources are listed at the bottom. Where a fact came from a third-party summary rather than Meta, it is marked (3rd-party).

## 1. The pitch

**One sentence in, an in-network appointment held in minutes.** A patient says what they need. An agent places 15 calls at once to simulated offices, finds out which actually take the plan and have an opening, negotiates honestly, and holds the best slot. The patient approves. Payoff: a live "directory vs. reality" counter showing how wrong provider directories are.

- **Theme:** Build for Your World. Finding an in-network appointment that actually exists is a problem the team knows firsthand from healthcare operations.
- **Track:** Startup (decided: two-person team). Judged on technical execution and whether it holds up in production. The swarm demo is still the opening, but a large share of the score now rides on reliability, evals, cost and latency numbers, a credible compliance posture, and a believable path from simulated offices to a real pilot. See section 5b.

## 2. Hackathon facts (verify against Meta's Official Rules once the team accepts them)

| Item | Detail |
|---|---|
| Build window | Oct 26 to Nov 4, 2026 |
| Submission deadline | **Nov 4, 9:00 PM ET** (3rd-party). Judging Nov 4 to 8, live finals Nov 9. |
| Prizes | $1M total, split not published |
| Required tools | None mandated. Menu: Muse Spark, Muse Wonder, Muse Image, SAM 3.1 via the Meta Model API; open weights; Muse Code |
| Credits | $150 Meta Model API (sources disagree on who gets it); Baseten $100, Modal $100, Fireworks $25 for selected participants |
| Not stated anywhere I could find | Team size, healthcare/PHI rules, phone-call rules, submission format, whether non-Meta tools are allowed |

**Plan for the unknowns:** nothing in this design uses real PHI or calls real clinics. Everything is simulated and labeled so on screen.

## 3. Which Meta tool does what

| Piece | Meta tool | Why |
|---|---|---|
| Call worker (15 concurrent) | `muse-spark-1.3` via Meta Model API | Parallel tool calling, tuned for agentic work, 3,000 RPM / 4M TPM per team |
| Planner and critic | `muse-wonder-1.0` (preview) | Built for long-horizon agentic work, "Active Focus" recovers from errors; $4 / $20 per 1M tokens, so use it sparingly |
| Patient intake from text | Wonder, structured output | Utterance to constraints JSON |
| Insurance card reading | Muse Spark vision (image input) | Card photo to payer, plan, member ID. Fake card only |
| Realtime speech-to-text | `muse-voice-transcribe-1.0` over WebSocket | $0.18/hr, turn detection and speaker labels, 256 concurrent streams, enough for 15 calls |
| Simulated receptionists at volume | **Muse Spark Open** (open weights) on Fireworks or Baseten | Uses partner credits, avoids Meta rate limits during 200-call evals, and lets you say you used both closed and open Muse |
| Demo assets | Muse Image | Synthetic insurance card and clinic logos |
| Stretch: portal booking | Meta's computer-use guide (`/docs/computer-use`) | Fills a fake booking portal when no phone is needed |
| Building the thing | Muse Code | Meta's agentic coding tool; counts as using the stack |

**What Meta does not have:** text-to-speech or speech-to-speech. The docs state Muse Voice Transcribe is speech-to-text only. The voice layer therefore needs a non-Meta TTS (local open-source such as Piper or Kokoro, or a hosted one). Confirm the Official Rules allow this. Fallback: the dashboard speaks office lines with the browser's built-in speech, and the Meta transcription path is shown on a recorded clip.

**Note:** early planning assumed the "Llama API". Meta retired `api.llama.com` on July 6, 2026. Everything now goes through the Meta Model API at `https://api.meta.ai/v1`, which is OpenAI-compatible. The Twilio, Pipecat, and WhatsApp suggestions from earlier only matter for a real-world pilot, not for this build.

## 4. What exists today (built Oct 27)

Runs fully offline in mock mode; **not yet run against the live Meta API** (no key in this environment).

- Meta client wrapper (OpenAI SDK, per-role models, retries, concurrency cap)
- Immutable safety block with a hash, and a worker with **no tool that can confirm a booking** (enforced by construction)
- 12 receptionist personas in the mix (one friendly baseline, the rest adversarial; Spanish-speaking is defined but not yet in the mix), 2 IVR phone trees, simulated hold time
- Fixed 15-office demo swarm: the best slot (Nov 2, 10:00) sits behind the Transferrer so honest leverage from earlier offices exists when it finally picks up
- Shared blackboard (workers see held **times** only, never other offices' names)
- Deterministic judge against hidden ground truth plus safety checks, with tests proving it fails a leaky worker
- FastAPI + SSE + live 15-tile dashboard, truth counter, audit log, patient approve button
- Batch eval CLI with dev/holdout split and prompt and safety hashes
- 19 tests passing

## 5. Schedule to the deadline

| Day | Date | Goal | Done when |
|---|---|---|---|
| 1 | Tue Oct 27 | Vertical slice (done offline) | `pytest` green; **`scripts/smoke_meta.py` run with a real key and every line says PASS** |
| 2 | Wed Oct 28 | Real-model calibration | 20 scenarios on live models; read transcripts; fix worker prompt and personas; first real swarm of 15 on screen |
| 3 | Thu Oct 29 | Honest negotiation and intake | Leverage visible in a real run; text-to-constraints via Wonder; card photo via vision |
| 4 | Fri Oct 30 | Evals at scale | 150 to 200 calls using Muse Spark Open receptionists; LLM-judge quality scores; **baseline v0 number recorded**; SQLite run store; cost and latency recorded per call |
| 5 | Sat Oct 31 | Self-improvement loop | Wonder critic clusters failures, proposes prompt patches; accept only if held-out success rises and safety stays 100%; chart v0 to v3 |
| 6 | Sun Nov 1 | Voice layer | 3 featured tiles with real audio: TTS to Muse Voice Transcribe realtime to worker; mic intake |
| 7 | Mon Nov 2 | Polish and record | Dashboard polish, seeded demo, **backup video recorded**, architecture slide, README; **production-readiness checklist (5b) green**; Docker image builds and runs |
| 8 | Tue Nov 3 | Freeze and submit | Code freeze midday, rehearse twice, **submit tonight** |
| 9 | Wed Nov 4 | Buffer only | Deadline 9 PM ET. Do not plan work here |

**Cut order if behind:** computer-use booking, then multilingual, then cost reasoning, then voice tiles (keep the text swarm). Never cut: the 15-tile swarm, honest leverage, the truth counter, the eval chart.

## 5b. Startup track: what changes

The startup rubric is technical execution and production readiness, so the extra effort goes here, not into more demo features. Items marked (new) do not exist yet.

**Production-readiness checklist (aim to show each one working, not described):**
1. **Reliability:** per-call timeouts, retry with backoff on rate limits (client already retries 429s), one failed call never stops the swarm (done), global swarm deadline (new), graceful fallback to a "callback card" for the patient when the bot cannot complete a call (partly done via escalation).
2. **Telephony adapter (new):** a `CallChannel` interface with the simulated office as one implementation and a Twilio-shaped stub as the second. This is the honest answer to "how does it reach a real clinic?" without making real calls.
3. **Persistence and audit (new):** SQLite store for runs, calls, transcripts and scores; the event log already doubles as an audit trail. PHI-safe logging: redact member ID and DOB in logs.
4. **Observability (new):** per-call cost, latency, turns and tool errors, shown on the dashboard and in the eval summary. These are the numbers a startup judge asks for.
5. **Evals with discipline:** dev/holdout split (done), safety pass rate must stay at 100% (done), report per-persona results, baseline vs improved on the holdout set (Days 4 to 5).
6. **Compliance posture (written down, not built):** consumer-app data path, consent record, data minimization (done in code), vendor BAAs needed before real PHI, recording-consent and AI-disclosure rules for real calls. One page in `docs/COMPLIANCE.md` (new). Do not claim HIPAA compliance; claim a design that is compatible with it.
7. **Packaging (new):** Dockerfile, `.env.example` (done), health endpoint, a CI run of the test suite.
8. **Pilot path (one slide):** opt-in practices first; truth graph as the data asset; buyers are care-coordination teams and health plans who already pay people to make these calls.

**Two-person split:**
- **Person A, agent and evals:** worker prompt calibration, persona realism (real front-desk behavior), judge, self-improvement loop, cost and latency metrics, run store.
- **Person B, product and demo:** dashboard, intake and card photo, voice layer, Docker and CI, telephony adapter, compliance one-pager, pitch and video. Person B also reads the Official Rules.
- **Both, daily:** 15 minutes at the end of each day to merge and run the full swarm together. Keep one `main` branch, small commits, and never change the safety block or the holdout split without telling the other person.

**Cut order for the startup track:** computer-use booking, multilingual, voice tiles, cost reasoning. Protect the checklist above, the swarm, honest leverage, the truth counter and the eval chart.

## 6. Risks to watch

1. **Muse Spark 1.3 audio support is incomplete** per Meta's docs; use `muse-spark-1.2` if you ever feed it audio directly. Our path uses the dedicated transcribe model instead.
2. **Muse Wonder is a preview**, standard mode only. Keep Spark as a drop-in fallback (`PLANNER_MODEL=muse-spark-1.3`).
3. **tool_choice only supports "auto"**: the worker must handle replies with and without tool calls. The code does.
4. **Contributor models** (`-contributor`, about $0.10/$0.20 per 1M) let Meta train on your prompts and cap at 100 RPM. Fine for simulated data only, never real PHI, and too slow for the 15-way swarm.
5. **Cost** (rough estimate, unmeasured): about 16 model requests per call at a few thousand input tokens each suggests roughly $0.05 to $0.15 per call on Spark 1.3. A 200-call eval is then on the order of $10 to $30. Measure on Day 2 before trusting this.
6. **Model behavior is unknown until Day 2.** The mock proves plumbing, not quality. Expect to spend real time on prompts.

## 7. Open decisions

1. Does each teammate have their own Meta Model API key and credits? Each selected participant should.
2. Get the Meta Model API key and credits, then run `python scripts/smoke_meta.py`.
3. Read the Official Rules once published: non-Meta TTS allowed? any healthcare data or phone-call restrictions? submission format (video length, repo, demo link)?

## Sources

- [Meta Model API docs](https://dev.meta.ai/docs): endpoints, models, tool calling, voice, pricing and rate limits (Meta)
- [Muse Wonder announcement](https://about.fb.com/news/2026/10/introducing-muse-wonder-models/) (Meta)
- [Muse Spark on Meta Model API](https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/) (Meta)
- [Muse Spark Open deployment](https://dev.meta.ai/docs/muse-spark-open/deploy) (Meta)
- [Hackathon details](https://vibecoderslife.com/post/meta-ai-developer-hackathon-2026) (3rd-party)
- [Hackathon announcement](https://superpowerdaily.com/posts/meta-sets-october-26-start-for-1-million-ai-hackathon-capped-at-20-000-builders) (3rd-party)
- [Muse Spark 1.3 integration guide](https://therouter.ai/blog/meta-muse-spark-13-api-integration-routing-guide/) (3rd-party)
- [Promptfoo Meta provider](https://www.promptfoo.dev/docs/providers/meta/) (3rd-party)

The three earlier design docs in this folder (`swarm-architecture.md`, `receptionist-simulator.md`, `demo-script.md`) still describe the product design. Where they mention Llama, Pipecat, Twilio or "native speech-to-speech", this plan supersedes them.
