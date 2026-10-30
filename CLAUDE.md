# CLAUDE.md: project context for future sessions

Read this first, then README.md (the full framework). Updated Oct 29, 2026. The repo is **public**: keep names, employers and other personal details out of it. All data is fictional.

## What this is (direction changed Oct 27, widened Oct 29)

**Philosophy (Oct 29).** Put the power in the patient's hands to use every benefit and resource they already have. Healthcare is extremely complicated for the average person; AI does the complicated work so it's simple for them. PJ uses each person's risk factors to drive outreach and actions, and it works for a whole family: an older parent, a child, the person themself. The home screen is a **menu of actions** ("What should PJ do?"), not a dashboard or a chatbot; chat and the buckets sit lower on the page. See `docs/FAMILY-AND-AGING.md` (YC "AI for the Aging Population" fit and the market landscape).

**Demo pitch:** `docs/DEMO-PITCH.md` is the 3-minute script. **Update it in the same change as any user-visible feature.**

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

`MOCK_LLM=1 HOLD_SCALE=0 pytest -q` passes **162 tests**.

**Partner credits: scale and adversaries (Oct 29, late).** THE RULE: the patient-facing crew stays on Meta's Model API (enforced in `ai.model_for`); Muse Spark Open on partner credits runs simulators, adversaries, judges. Results and the running spend log: `docs/evals.md` (rebuilt by every eval script from `docs/evals/*.json` + `spend.jsonl`); the page is `/gym`.

| Piece | Files | Live result |
|---|---|---|
| Adversarial plan reviewer: Muse Spark Open plays the insurer's reviewer, tries to deny the draft appeal against the plan's own rules; Spark writer revises (≤3 rounds); leftover objections become to-dos. Step "Stress-test the appeal" between draft and approve | `src/agents/reviewer.py`, `workflows._pa_review`, `scripts/stress_test_appeal.py` | strong file + generic letter: 4 objections → 1 revision → no reason to deny; thin file: 4 evidence gaps → to-dos |
| Call gym: 16 kinds of hard fictional offices (data fishers, fake HIPAA verification, AI refusers, transfer loops, menu maze, voicemail, hold drop, Spanish-first, mishearing, hostile…), deterministic from a seed; scored in code | `src/sim/gym.py`, `src/eval/gym.py`, `scripts/call_gym.py` | 600 calls (fresh seed 9, after prompt fixes): **100% safe**, 100% right outcome, p50 20 s, p95 38 s, $0.032/call. History: seed 7 found 3 failures (Spanish "IA", a spelled-out reference, refusers ended without handing back); the judges then caught 45 ambiguous "Yes, I'm an AI" answers in seed 8 |
| Cross-family judges (Meta Spark vs Muse Spark Open), fixed rubric, Cohen's kappa | `src/eval/judges.py`, `scripts/judge_evals.py` | 100 items, run twice: kappa 0.87 and 0.84, ~99% agreement, 5–6 disagreements per run listed |
| Reader eval: 33 fictional docs × 4 photo qualities (clean, phone, messy, harsh) | `src/sim/documents.py` (`eval_documents`), `src/eval/messy.py`, `scripts/eval_reader.py` | 99.6 / 99.6 / 99.3 / 90.9% fields |
| Voice loop: office lines synthesized, transcribed by Muse Voice Transcribe, caller hears only the transcript; browser player with waveform + captions on `/gym` | `src/voice_loop.py`, `src/voice_tts.py`, `src/voice.py` (`transcribe_pcm24k`), `scripts/voice_call.py`, `scripts/eval_asr.py` | ASR: DOB 100%, reference 100%, names 35% exact |

- **Providers per role:** `<ROLE>_PROVIDER=meta|baseten|fireworks` (`src/config.py` `PROVIDERS`). Defaults: `reviewer` → Baseten, `judge_open` → Fireworks, `office` → Meta unless `OFFICE_PROVIDER=fireworks` (the gym sets it). Open-weights hosts get JSON mode with the schema in the prompt (`ai.chat_json`).
- **The Baseten hackathon key works only with `meta-models/muse-spark-open-1026`** (Baseten's docs say `meta-models/muse-spark-open`; that name returns 403 "please check the api-key" with this key). It can't create deployments either, so no TTS on Baseten with it. The reviewer runs on Baseten by default; up to 2M tokens per minute.
- **TTS is off by default** (`VOICE_TTS=off`): non-Meta TTS isn't confirmed allowed by the Official Rules. `/voice/*` returns 404 and `/gym` shows captions only while it's off. The demo recording was made with Kokoro-82M (open weights) run locally: the Baseten hackathon key is scoped to one model and can't deploy a TTS model.
- **Meta realtime ASR** (`wss://…/asr/realtime`) answered HTTP 400 from the sandbox; `transcribe_pcm24k` falls back to file transcription (same model) and records which route ran.
- Every eval script logs spend; the gate is $25 per run and 70% of a partner credit (`evals_md.over_limit`, `--per-call-usd`).
- Tests: `tests/test_partner_credits.py`.
- **Claim checker** (`src/agents/claims.py`, role `verifier`, default provider `modal`: Qwen3.6-35B-A3B on a Modal *dedicated* endpoint at `MODAL_ENDPOINT_URL` with `MODAL_PROXY_TOKEN` = `<id>.<secret>`). Lists every factual claim in a letter with the FACTS words that back it; code drops claims not in the letter and overrules "supported" without a real quote. Any unsupported claim → one writer repair (`appeals.repair_letter`) → else the standard letter. Reviewer revisions get the same check. Not configured → the letter is marked "claims weren't checked". Eval: `scripts/eval_claims.py` (planted claims); live on Fireworks as a stand-in: 8/8 caught, 0/4 false flags. **Never use a Modal Shared endpoint: plan credits don't cover shared-endpoint tokens.** The endpoint host is `*.modal.direct`; `Authorization: Bearer <id>.<secret>` passes its proxy (no header → "proxy auth required"). On Oct 30 it answered 503 "no upstreams available" at once, with no cold start: no replica running, so start it / set min replicas ≥ 1 in Modal. Appeal facts list only what's really enclosed (`workflows.pa_enclosures`): a requested doctor's letter is marked "(not enclosed)", which was the source of the checker's enclosure flags.
- Keep the gym's caller-prompt SHA (`caller_prompt_sha` in the report) in mind: any edit to `prompts/office_caller_v0.txt` means re-running the gym on a fresh seed before quoting numbers.

**Family care and agent workflows (Oct 29). Offline, deterministic, simulated counterparties.**

| Area | Files |
|---|---|
| Care circle: parent of a minor (ends at 18), consented helper, legal representative, pending consent | `src/agents/circle.py` |
| Risk factors → support plan (Wellness Visit, falls, med review, rides, cost help, caregiver support…) | `src/agents/outreach.py` |
| Action-menu home screen | `src/agents/actions.py`, `home.html` |
| Crew workflows: office request, bill dispute, prior-auth appeal (+ outside review), plan resources, DME, caregiving-hours appeal, counselor request | `src/agents/workflows.py`, `src/sim/counterparties.py` |
| Caller: phones the PCP office (menu, hold, transfer, reference number, transcript) | `src/agents/office_calls.py`, `src/sim/pcp_office.py` |
| Demo family: Alex, mom Rosa (78, Medicare Advantage, POA), son Leo (9, Medicaid) | `src/patient/demo.py` |
| Tests | `tests/test_family.py` |

**PJ's crew on Meta models (Oct 29), verified live:**

| Agent | Model | Files | Live result |
|---|---|---|---|
| Caller: phones the PCP office (menu, hold, transfer), refuses data fishing, reference must be heard on the call | Muse Spark (and Spark receptionists) | `src/agents/office_caller.py`, `src/sim/pcp_office.py` (`OfficeLine`) | 12–22 s, 11–17 requests, every check passed |
| Reader: denial letter, bill, EOB from a photo; validated; image not kept | Spark vision, JSON schema | `src/agents/reader.py`, `src/sim/documents.py` | `scripts/eval_reader.py` 25/25 fields |
| Strategist: evidence → the plan's own rules; invented citations dropped | Muse Wonder | `src/agents/appeals.py` | ok |
| Writer: appeal and dispute letters; `check_letter` gates the signature | Spark | `src/agents/appeals.py` | 5/5 checks |
| PJ's chat: tools `find_care`, `propose_job`; crisis and medical pre-filters; reply scanner | Spark | `src/agents/guide.py` (`ask_live`) | `scripts/redteam_pj.py` 20/20 |

- `src/agents/ai.py` meters every patient-layer request (`PJ_AI_DAILY_REQUESTS`, `PJ_AI_ACCOUNT_REQUESTS`), refuses `-contributor` models, and every model step falls back to the rules (`engine: "rules"` on screen).
- Model steps return `workflows.Pending` and run in a background thread (`PJ_BACKGROUND`, auto = on unless mock); the UI polls while `busy` and streams call transcripts.
- The prebuilt demo family is built with `live=False`, so loading the demo spends nothing.
- **Token caps include reasoning tokens.** A 500-token cap on Spark returned empty replies; keep caps generous (see `max_tokens` in each agent).
- Tool results must come right after the assistant's tool calls; return what the line said inside the tool result (fixed a bug where it was a separate user turn).
- Storage: SQLite via `PATIENT_DB` (set in the Dockerfile), session tokens stored only as hashes, `DELETE /api/p/me`.
- Swarm live runs are **open to anyone during judging** (`OPEN_LIVE_DEMO=1` default, still capped by `MAX_LIVE_RUNS_PER_DAY` and `MIN_SECONDS_BETWEEN_RUNS`). Set `OPEN_LIVE_DEMO=0` to require `APP_ACCESS_TOKEN` again.
- Partner credits: Fireworks and Baseten keys go in `FIREWORKS_API_KEY` / `BASETEN_API_KEY`; point a role with `<ROLE>_API_KEY_ENV`, `<ROLE>_BASE_URL`, `<ROLE>_MODEL`. Rule: patient-facing crew stays on Meta's API; partner credits are for simulators, adversaries and evals.

There is **no telephony**: the agents are live, the offices are simulated. A phone channel would sit behind the same interface as `FaxChannel`.

**Live demo:** https://swarm-scheduler.72q91gp7bkhmc.us-west-2.cs.amazonlightsail.com/ (AWS Lightsail, one container). It redeploys automatically on every merge to `main` once the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` repo secrets exist; until then, use `python scripts/deploy_lightsail.py`. See DEPLOY.md and `docs/aws-hosting.md`.

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

- Card reading, navigator copy and records extraction are still rules (`TODO(meta)`); the reader pattern in `reader.py` is the template.
- "Do it, PJ" on an in-network pathway records a task but **does not start the swarm yet**. This is README next-step #2.

**Swarm.**

What exists:

- Meta client, immutable safety block, tool-calling worker.
- 12 personas and 2 IVR trees, plus a 15-office demo scenario.
- Blackboard and dispatcher.
- Deterministic judge and batch eval CLI.
- SSE dashboard.
- Token-gated live runs and public replay.
- Dockerfile, `render.yaml`, CI.

**Verified on the live Meta API (Oct 27):**

- `scripts/smoke_meta.py` passes every check.
- A full 15-call swarm ran on `muse-spark-1.3`: 15/15 calls, 15/15 safety, about 25 s. That run is the public replay (`recordings/demo.jsonl`). The best slot was won by honest leverage: the worker cited a real held slot, and an office released a hidden cancellation.
- Voice intake: the 🎙 button on `/swarm`, transcribed by Muse Voice Transcribe file transcription (`src/voice.py`).

**Real provider data (`src/directory/`):**

- An NPPES snapshot of 677 Phoenix-metro cardiologists.
- Plan-Net FHIR network claims from UHC, Cigna and Humana.
- A directory tab on `/swarm`.
- The swarm's step 1 is a real directory search. The simulated offices borrow only a city: no real name, NPI or phone reaches a simulated office.
- See `docs/provider-data.md`.

**Not verified:**

- Cost per call is an unmeasured estimate (about 16 requests per call).

**History note.** Everything from the live-API runs onward was built on branch `claude/pensive-hypatia-crv7nq` and folded into `main` on Oct 27, by replaying its commits on top of the patient-first work. `main`'s history had been squashed, so the two branches shared no commits. Develop from `main`.

## Next steps

Family-layer next steps are in `docs/FAMILY-AND-AGING.md`. Highest value before judging (partner credits): an adversarial plan reviewer on Muse Spark Open (Baseten), a call gym of hundreds of simulated receptionists on open weights (Fireworks), cross-family judges, a bigger reader eval, and a real voice. Steps 3, 9 and 12 below are done.


The ordered list, with acceptance criteria, is in README section 15. In short:

1. Point the Care Team agent at the real directory (`src/directory/`) for UHC, Cigna and Humana.
2. Wire "Do it, PJ" (in_network) to a swarm run whose held slot shows on the patient dashboard.
3. Put PJ's chat on Muse Spark, with a hashed safety block and a red-team set at 100%.
4. Read card photos with Spark vision.
5. Build a simulated insurer portal and drive it with computer-use.
6. Have Wonder write navigator plans.
7. Extract records PDFs into `HealthItem`s.
8. Build the Referrals agent.
9. Add SQLite and delete-my-data.
10. Reuse the swarm's voice intake (`src/voice.py`) for Ask PJ.
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
| `src/directory/` | Real NPPES + Plan-Net provider data (snapshots in `data/directory/`) |
| `src/voice.py` | Muse Voice Transcribe for the 🎙 intake |
| `scripts/deploy_lightsail.py`, `.github/workflows/deploy.yml` | Lightsail deploys (manual / on merge) |
| `src/api/static/index.html` | Swarm dashboard, served at `/swarm` |

**Docs:** `docs/DEMO-PITCH.md` (keep current), `docs/COMPLIANCE.md`, `docs/FAMILY-AND-AGING.md`, `DEPLOY.md`, `docs/PLAN.md` (the original swarm plan; still valid for the swarm), `docs/DATA-SOURCES.md` (FHIR, Blue Button, sandboxes, public data).

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
9. **Care circle consent.** An adult is invisible until they consent (typing their own name). A helper may act but never sign for an adult; only a parent of a minor or an attested legal representative signs, and the signature names the capacity.
10. **Workflow consent gate.** No `send` step runs before its `approve` step is signed by someone allowed to sign. A "no" escalates; it never silently ends.
11. **Outreach never advises.** Support actions name covered services and resources only; a test scans them for diagnostic or dosing language.
12. **The caller discloses it's an AI** to every person it reaches, and shares only name, DOB, member ID and plan. It uses the same `SAFETY_BLOCK` as the swarm.
13. **`PJ_SAFETY` is immutable;** `PJ_SAFETY_SHA` is pinned in `tests/test_spark_crew.py`. The PJ red team stays at 100%, offline and live.
14. **Models are checked, never trusted:** a reference must appear in what the office said; letter numbers must come from the facts; citations must exist; money math is code; uploaded images are never stored.
15. **Crisis words and medical questions never reach a model** in PJ's chat. PJ only proposes work; a person taps to start it.
16. **Partner credits never face the patient.** The caller, reader, strategist, writer and PJ's chat run only on Meta's API (`ai.model_for` refuses other endpoints). Muse Spark Open runs simulators, the reviewer and judges.
17. **Every claim in a letter needs a fact behind it** (claim checker), and **the reviewer is an adversary, not an author.** Its objections must cite rules that exist; it never writes letter text; revisions must pass `check_letter` against the original facts. If it's unavailable, the step is skipped with a note.
18. **Caller safety is 100% in the call gym.** If a gym safety check fails, fix `prompts/office_caller_v0.txt` (never `SAFETY_BLOCK`) and re-run on a fresh seed.
19. **No real phone numbers or voices, ever.** Voice calls are labeled "simulated call, synthetic voices"; TTS stays off unless the rules allow it.

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
