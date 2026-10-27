# CLAUDE.md: project context for future sessions

Read this first, then README.md (the full framework). Updated Oct 27, 2026. The repo is **public**: keep names, employers and other personal details out of it. All data is fictional.

## What this is (direction changed Oct 27)

**PJ Health: healthcare built for the patient, not the doctor.** A patient dashboard where PJ (the GLTrax Gila monster, they/them) guides someone through their own healthcare.

**Onboarding.** The patient signs in with a name only (demo, no password) and gives PJ three things. Agents do the hard part of each:

1. **Insurance card.** The Coverage agent works out what's covered, the referral rules and the EAP.
2. **Their doctor.** The Care Team agent "calls" the office to confirm the fax and network status, because directories are wrong.
3. **A signature.** The Records agent faxes a right-of-access request and tracks it.

**The four buckets.** Results land in plain-language buckets:

- **Life & Connection** (SDOH)
- **Clinicals** (labs etc.)
- **Routines** (diet, sleep, stress)
- **Family & Genes**

**Asking for care.** The patient says one sentence ("I think I need to see a therapist"). The Care Navigator returns ranked options: EAP, in-network (truly), PCP referral first, telehealth, Medicare, Medicaid, community / 211, self-pay. Crisis words always get 988 / 911 first.

**The swarm.** The original build in this repo is the **Scheduling Swarm**: 15 parallel calls to simulated offices to hold an in-network slot. It is now *one capability PJ uses* when the patient picks "Do it, PJ" on the in-network option. It lives at `/swarm`; the patient dashboard is `/`.

**Pitch.** "Patient first, provider second" versus MyChart-style "provider first, patient second". Messaging: "Healthcare built for the patient, not built for the doctor" / "Your healthcare, owned by you."

## The competition

Meta Global AI Developer Hackathon (Meta + Cerebral Valley).

- **Track and team:** startup track, team of two.
- **Theme:** "Build for Your World".
- **Dates:**
  - Build window: Oct 26 to Nov 4, 2026.
  - **Submission due Nov 4, 9:00 PM ET.**
  - Judging: Nov 4 to 8.
  - Finals: Nov 9.
  - These dates come from third-party summaries. Verify them against Meta's Official Rules.
- **Judging:** the startup track is judged on **technical execution and production readiness**, not just a demo.
- **Still unknown until the Official Rules are read:**
  - Whether non-Meta text-to-speech is allowed.
  - Any rules on healthcare data or phone calls.
  - Submission format (video length, repo, demo link).
  - Team-size limits.
- **Credits:**
  - Meta Model API: $150 per selected participant (sources disagree on who gets it).
  - Partner credits: Baseten $100, Modal $100, Fireworks $25.

## Status (honest)

`MOCK_LLM=1 pytest -q` passes **42 tests**: 16 patient tests and 26 swarm tests.

**Patient layer (new). Works offline and is deterministic.**

| Area | Files |
|---|---|
| Models, buckets, store, demo patient | `src/patient/` |
| PJ guide, Coverage, Care Team, Records, Care Navigator | `src/agents/guide.py`, `coverage.py`, `care_team.py`, `records.py`, `navigator.py` |
| Simulated insurers + EAPs, directory with planted errors, records office | `src/sim/payers.py`, `providers.py`, `records_office.py` |
| `FaxChannel` + `SimulatedFax` | `src/channels/fax.py` |
| Patient API | `src/api/patient.py`, under `/api/p` |
| Dashboard | `src/api/static/home.html` |

The dashboard was checked in headless Chromium at iPhone and desktop widths, with no overflow.

**Patient layer: NOT done.**

- **No Meta model is called anywhere in the patient layer yet.** Card reading, PJ chat, navigator copy and records extraction are all rules or mocks marked `TODO(meta)`.
- "Do it, PJ" records a task but **does not start the swarm yet**. This is README next-step #2.

**Swarm (original build).**

What exists:

- Meta client, immutable safety block, tool-calling worker.
- 12 personas and 2 IVR trees, plus a 15-office demo scenario.
- Blackboard and dispatcher.
- Deterministic judge and batch eval CLI.
- SSE dashboard.
- Token-gated live runs and public replay.
- Dockerfile, `render.yaml`, CI.

**Not verified. Do not assume these work:**

- **Nothing has been run against the live Meta API.** The first job is `python scripts/smoke_meta.py`.
- `recordings/demo.jsonl` is a **mock** recording.
- The Docker image was never built locally. CI builds it.
- Cost per call is an unmeasured estimate (about 16 requests per call).

## Next steps

The ordered list, with acceptance criteria, is in README section 15. In short:

1. Smoke-test the live API.
2. Wire "Do it, PJ" (in_network) to a swarm run whose held slot shows on the patient dashboard.
3. Put PJ's chat on Muse Spark, with a hashed safety block and a red-team set at 100%.
4. Read card photos with Spark vision.
5. Build a simulated insurer portal and drive it with computer-use.
6. Have Wonder write navigator plans.
7. Extract records PDFs into `HealthItem`s.
8. Build the Referrals agent.
9. Add SQLite and delete-my-data.
10. Add voice input.
11. Record the demo video and rewrite the demo script around the therapist story.
12. Write `docs/COMPLIANCE.md`.

If you have to cut, cut in this order: 10, 9, 7, 5.

## Meta Model API facts (verified from the docs on Oct 27, 2026)

**Endpoint and key**

- The API is OpenAI-compatible. Base URL: `https://api.meta.ai/v1`.
- The key lives in the env var `MODEL_API_KEY` and must be **passed explicitly**; the OpenAI SDK does not read it.
- The old Llama API (`api.llama.com`) was **retired July 6, 2026**. Do not use Llama.

**Models**

| Model | Notes |
|---|---|
| `muse-spark-1.3` | Workhorse. $1.25 in / $4.25 out per 1M tokens. |
| `muse-wonder-1.0` | Preview, agentic. $4 / $20 per 1M tokens. |
| `muse-spark-1.2` | Use this if you send audio to a chat model; 1.3's audio support is incomplete. |
| `muse-voice-transcribe-1.0` | Speech-to-text. |
| `muse-image-1.0` | Images. |
| `sam-3.1` | Segmentation. |

- **Open weights:** Muse Spark Open (816B MoE, 42B active), available via Fireworks (`accounts/fireworks/models/muse-spark-open`) or Baseten (`meta-models/muse-spark-open`).
- **`-contributor` variants** are cheap, but **Meta trains on your prompts** and they cap at 100 RPM. Use them for simulated data only, never real PHI.
- **Rate limits** are per team: 3,000 RPM / 4M TPM for Spark and Wonder.

**Tool-calling gotchas**

- `tool_choice` supports only `"auto"`, so never send it. Handle replies both with and without tool calls.
- On Chat Completions, tools nest under `function`.
- You must echo back **the full assistant message, including `tool_calls`**, before the `tool` messages. Omitting it returns a 400.
- Function names must match `^[a-zA-Z0-9_.-]+$`.
- Tool arguments are not guaranteed to be valid; validate them.
- `reasoning_effort` accepts minimal, low, medium, high or xhigh. Never send `none`.

**Speech**

Meta has **no text-to-speech and no speech-to-speech**. It offers realtime speech-to-text only:

- Endpoint: `wss://api.meta.ai/v1/asr/realtime`.
- Auth goes in a first JSON handshake frame: `{"authorization":{"accessToken":"Bearer <key>"},"audioEncoding":"PCM_24KHZ","model":"muse-voice-transcribe-1.0","mode":"PUSH_TO_TALK"}`.
- Audio is sent as binary PCM16 mono 24kHz frames. Send `{"type":"endStream"}` to finish.
- Cost and limits: $0.18/hr, up to 256 concurrent streams.
- Whether 8kHz mu-law (telephony audio) works is unconfirmed.

**Docs:** https://dev.meta.ai/docs. Relevant pages: models, tool-calling, speech-to-text, computer-use, pricing-rate-limits, muse-spark-open/deploy.

## Where things are

See the layout table in README section 14. Key files:

**Patient layer**

| File | What it is |
|---|---|
| `src/patient/models.py` | Data model |
| `src/agents/guide.py` | PJ, including `PJ_SAFETY` |
| `src/agents/navigator.py` | Care Navigator: `CRISIS`, `NEEDS`, `navigate()` |
| `src/api/patient.py` | Patient routes |
| `src/api/static/home.html` | Dashboard |

**Swarm**

| File | What it is |
|---|---|
| `src/llm.py` | Client (`get_llm(role)`) |
| `src/config.py` | Per-role models |
| `src/safety.py` | Safety block and checks |
| `src/agents/worker.py` | Call worker |
| `src/sim/` | Simulated offices |
| `src/swarm/` | Blackboard and dispatcher |
| `src/eval/` | Judge and batch evals |
| `prompts/worker_v0.txt` | The only prompt the improvement loop may edit |
| `src/api/static/index.html` | Swarm dashboard, served at `/swarm` |

**Docs:** `DEPLOY.md`, `docs/PLAN.md` (the original swarm plan; still valid for the swarm), `docs/DATA-SOURCES.md` (FHIR, Blue Button, sandboxes, public data).

## Invariants: do not break these

**Patient layer**

1. **Crisis first.** Crisis words get 988 / 911 as the first and only top option (`navigator.CRISIS`). `test_crisis_always_first` enforces this.
2. **PJ never diagnoses, gives doses, or tells anyone to start or stop a medicine.** Medical questions go to the doctor or the nurse line. `test_pj_never_answers_medical_questions` enforces this. When PJ moves onto Muse Spark, `PJ_SAFETY` becomes an immutable, hashed block, the same way `SAFETY_BLOCK` works.
3. **Nothing leaves without the patient's consent.**
   - A records request is never sent unsigned: `records.send` raises `NotSigned`.
   - The typed signature must match the patient's name.
   - Bookings need the patient's yes.
4. **Every fact carries `source` and `confidence`.** Directory data is `unverified` until PJ confirms it.
5. **No passwords.** Sign-in is name-only *only because* the data is fictional. Never ask for or store insurer or portal passwords. Real data requires real authentication first (README section 12).
6. **Fictional data only.** Any new insurer, provider, phone or fax number must be obviously fictional: use 555-01xx numbers and `SIM-` IDs.
7. **No real PHI to any model, and never anything to `-contributor` models.**
8. **Plain language on screen**, with the clinical term kept in `buckets.py` for mapping.

**Swarm**

1. **`SAFETY_BLOCK` in `src/safety.py` is immutable** to any self-improvement loop. Assert that `SAFETY_SHA` is unchanged. The safety pass rate must stay at 100%.
2. **The worker has no tool that books or confirms.** Only the patient confirms. A test enforces this.
3. **Data minimization.** The worker only ever gets name, DOB, member ID, plan, visit reason and constraints.
4. **Honest leverage only.** The worker may mention held *times* from `check_blackboard`, but never office names and never invented offers.
5. **Never tune on the `holdout` split.**
6. **Running the server:**
   - Live runs need `APP_ACCESS_TOKEN`.
   - Run **exactly one instance**; state (swarm and patients) is in memory.
   - Never commit `.env`.
7. **Simulated offices are always labeled as simulated** in the UI.

## History and decisions

- The project started as a voice agent calling insurers for benefits.
- It then became patient-facing appointment finding, built as the 15-way swarm.
- On Oct 27 it was **widened to the patient-first dashboard**, because the swarm alone is a feature, while "your healthcare, owned by you" is the product. The swarm stays as PJ's scheduling tool and as the demo climax.
- Eligibility (271) and payer FHIR APIs were explored earlier. The Node Blue Button sandbox starter is in `examples/blue-button-node/` and is not part of the build. `docs/DATA-SOURCES.md` maps sandboxes, synthetic data, directories and formularies.
- Earlier docs in `docs/` mention Llama, Pipecat and Twilio. They carry a banner saying the stack is now the Meta Model API.
- Names are deliberately omitted from this public repo.
