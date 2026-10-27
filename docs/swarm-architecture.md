# Swarm Booking Agent: Architecture

> **Design note.** Early product design. Where this mentions Llama, Pipecat, Twilio or speech-to-speech, the current implementation uses the Meta Model API (Muse Spark / Muse Wonder / Muse Voice Transcribe); see the README. All offices and patients are simulated.

Goal: one spoken sentence from the patient becomes a held, in-network appointment in minutes, by calling many offices in parallel and negotiating honestly.

## 1. System overview

```
Patient (voice / insurance-card photo)
        |
   [Intake Agent]  -> PatientProfile + Constraints + ConsentRecord
        |
   [Planner Agent] -> Plan (strategy per provider)
        |
   [Directory Service] -> ranked candidate Providers (NPPES + payer directory)
        |
   [Dispatcher] --spawns--> N x [Call Worker]  (concurrent)
        |                         |  \
        |                         |   -> Strategy ladder: portal (computer use) -> voice -> callback
        v                         v
   [Blackboard / shared state] <--- structured Outcomes + Offers (live)
        |
   [Negotiator + Ranker] -> best slot -> HOLD (never auto-confirm)
        |
   [Dashboard (WebSocket)]   [Audit Log]   [Truth Graph]   [Eval/Improve Loop]
        |
   Patient approves in app -> final confirmation call/click
```

## 2. Components

### Intake Agent
- Voice in, structured out: specialty, location radius, earliest/latest times, urgency, language.
- Insurance card photo: extract payer, plan name, member ID, group number (vision). Show extracted values for patient confirmation.
- Produces a `ConsentRecord`: patient authorizes the agent to call on their behalf and to share the minimum data fields listed. Timestamped, stored, shown on dashboard.

### Planner Agent
- Frontier model with tool calling. Owns the goal and the budget (max calls, max time, max retries).
- Chooses strategy per provider:
  1. Online booking page found -> computer-use worker (submit only after patient approval of the slot).
  2. Else voice call.
  3. Else (AI refused / no answer) -> send patient a callback card with a ready script.
- Replans when outcomes arrive (e.g. "3 offices need a referral" -> asks patient if they have one).

### Directory Service
- Sources: NPPES API, payer provider directory (FHIR Plan-Net where available), optional aggregator.
- Normalizes to one `Provider` shape (see schemas). Each plan-acceptance claim carries a confidence score and `last_verified`.
- Ranking inputs: distance, specialty match, network confidence, historical bookability from the Truth Graph.

### Dispatcher + Call Workers
- Dispatcher keeps K calls in flight (e.g. 15), respecting office hours and per-provider cooldowns.
- Each worker is an independent realtime voice session with:
  - System prompt (see Section 5).
  - Tools: `press_dtmf`, `record_outcome`, `record_offer`, `request_human`, `end_call`, `check_blackboard` (read-only snapshot of best current offer).
  - Hard disclosure at call start: "Hi, I'm an AI assistant calling on behalf of a patient."
- Voice stack options: native speech-to-speech model, or STT -> LLM -> TTS via Pipecat. Telephony via Twilio/Telnyx for real calls; for the demo use simulated offices (Section 3).

### Blackboard (shared state)
- Redis or in-memory store keyed by `request_id`.
- Holds: all `CallTask` states, all `Offer`s, current `best_offer`, patient constraints.
- Workers read a snapshot, never raw transcripts from other calls (keeps PHI separated per call).

### Negotiator + Ranker
- Scores offers: `score = w_time * earliness + w_dist * proximity + w_conf * network_confidence + w_cost * est_cost_delta - penalties(referral_needed, new_patient_closed)`.
- Negotiation policy (see Section 4) runs inside workers using the blackboard snapshot.
- Picks a winner and places a HOLD. Patient approves in-app; only then does the system confirm.

### Dashboard
- WebSocket feed of events: `call_started`, `ivr_navigating`, `on_hold`, `utterance` (live transcript), `outcome_recorded`, `offer_received`, `best_offer_changed`, `escalated`.
- Views: swarm grid (one tile per call with status color), live transcript drawer, offer leaderboard, truth-graph delta ("directory said X, reality was Y"), cost reasoning panel.

### Truth Graph
- Edges: `(Provider)-[ACCEPTS {plan, confidence, last_verified, source}]->(Plan)`; node attrs: new-patient status, referral requirement, bookability channel (portal / AI call / human only).
- Every call outcome updates confidence. Confidence decays with time. Surfaces "directory wrong" stats for the demo.

### Audit Log
- Append-only: consent, every tool call, every disclosure, every data field shared, every escalation, patient approvals.

## 3. Simulated offices (demo + eval mode)
Two modes behind one interface `OfficeEndpoint`:
- **Text sim:** worker talks to a receptionist LLM over text. Fast, cheap, thousands of runs for evals.
- **Voice sim:** receptionist LLM + TTS/STT bridged to a phone number or in-app audio channel. Used for the live demo.
Same prompts and hidden state in both. See `receptionist-simulator.md`.

Never call real clinics in the demo or evals.

## 4. Negotiation policy (honesty constraints)
Allowed:
- State true constraints ("The patient can only do mornings after 9").
- Reference a real held offer from the blackboard ("I currently have a Thursday at 2pm elsewhere. Do you have anything earlier?"), only if that offer exists and is still held.
- Ask for waitlist or cancellation list placement.

Forbidden:
- Fabricating competing offers, deadlines, or urgency.
- Claiming to be human or the patient.
- Sharing more than the minimum fields (name, DOB, plan, member ID, reason for visit category).
- Accepting or confirming a booking without patient approval (workers can only HOLD / "pencil in" where the office allows it).

## 5. Call worker prompt skeleton
```
You are an AI assistant calling a medical office on behalf of a patient.
Open with: "Hi, I'm an AI assistant calling on behalf of a patient. Is this a good time for a quick scheduling question?"
If asked, confirm you are an AI. Never claim to be human.

Goals, in order:
1. Confirm the office accepts {payer} {plan_name}.
2. Confirm they accept new patients for {specialty}.
3. Ask whether a referral is required.
4. Get the earliest 2-3 slots matching: {constraints}.
5. Ask to place a tentative hold for the best slot. Do NOT confirm a final booking.

Share only: patient name, DOB, member ID, plan, visit reason category. Refuse anything else (SSN, address beyond ZIP, payment info).
Use tools to record structured outcomes as soon as you learn each fact.
If the office refuses AI callers or you are unsure, call request_human and politely end the call.
Navigate IVRs with press_dtmf. Wait through hold; do not hang up before {max_hold_minutes}.
Negotiation: follow the honesty rules. Only reference offers returned by check_blackboard.
Be brief, polite, and natural. Read back key details (date, time, provider, plan acceptance) before ending.
```

## 6. Data schemas

```json
// Provider
{ "npi": "string", "name": "string", "specialty": "string",
  "address": {"line": "", "city": "", "state": "", "zip": ""},
  "phone": "string", "booking_url": "string|null",
  "network": [{"plan_id": "", "status": "in|out|unknown", "confidence": 0.0, "last_verified": "ISO8601", "source": "directory|call|portal"}] }

// CallOutcome (recorded via tool, incrementally)
{ "request_id": "", "npi": "",
  "reached_human": true, "refused_ai": false,
  "accepts_plan": "yes|no|unsure", "new_patients": "yes|no|unsure",
  "referral_required": "yes|no|unsure",
  "offers": [{"slot_start": "ISO8601", "provider": "", "held": true, "expires": "ISO8601|null"}],
  "escalation_reason": "string|null", "disclosed_ai": true,
  "fields_shared": ["name","dob","member_id","plan","reason_category"],
  "transcript_ref": "uri" }

// Offer (blackboard)
{ "offer_id": "", "npi": "", "slot_start": "", "held": true, "score": 0.0, "created_at": "" }
```

## 7. Concurrency model
- Python `asyncio`: one task per call, shared `Semaphore(K)`.
- Event bus (in-process queue for hackathon; Redis streams if time) -> WebSocket server -> dashboard.
- Timeouts: per-call max duration, per-request global deadline, exponential backoff on busy/no-answer, max 2 retries.
- Idempotency: `call_id` per attempt; outcomes are upserts.

## 8. Self-improvement loop
1. Run a batch on the simulator (e.g. 100 office scenarios).
2. Score each run (Section 9). Cluster failures with an LLM (e.g. "gave up during hold", "shared too much", "missed referral question").
3. A critic agent proposes a targeted prompt/policy patch per cluster.
4. Re-run on a held-out set. Accept the patch only if success rises and safety metrics do not regress.
5. Immutable safety block (disclosure, data minimization, no auto-confirm, honesty rules) cannot be edited by the loop.
6. Log the version history and chart success rate per iteration (demo visual).

## 9. Metrics
- Task success: obtained >= 1 valid held offer matching constraints.
- Info accuracy: extracted facts vs. simulator ground truth.
- Disclosure compliance: 100% required.
- Data minimization violations: 0 required.
- Honesty violations (fabricated offers): 0 required.
- Escalation quality: escalated when it should have (precision/recall).
- Time-to-first-offer and time-to-best-offer.
- Directory error rate discovered.

## 10. Build order (48h)
1. One voice (or text) call against one simulated office, with structured outcome tools.
2. Dispatcher with concurrency + event bus + minimal dashboard grid.
3. Blackboard + ranker + honest negotiation.
4. Simulator personas + eval harness + score report.
5. Self-improvement loop + chart.
6. Intake (voice + card photo), truth-graph panel, cost reasoning.
7. Computer-use portal booking if time remains.

## 11. Risks and cuts
- Realtime voice latency across 15 concurrent calls: cap at 8-10 live voice, rest in text-sim mode, or pre-warm sessions.
- Demo-day network: keep a local fallback and a recorded run.
- Cut first: computer-use booking, multilingual, cost reasoning. Keep: swarm grid, negotiation, truth-graph delta, eval chart.
- Legal: recording consent and AI-voice rules apply to real calls. Demo only against simulated offices. Verify requirements before any real-world pilot.
