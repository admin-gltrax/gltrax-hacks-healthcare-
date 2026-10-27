# Demo Script (5 minutes + 1 minute Q&A buffer)

> **Design note.** Early product design. Where this mentions Llama, Pipecat, Twilio or speech-to-speech, the current implementation uses the Meta Model API (Muse Spark / Muse Wonder / Muse Voice Transcribe); see the README. All offices and patients are simulated.

Rule: every number on screen comes from a real run you can reproduce. No invented stats. Offices are simulated and labeled as such.

## Pre-demo checklist
- [ ] Swarm dashboard loads with 15 office tiles, simulated tag visible
- [ ] Seeded scenario: best slot lives behind the Transferrer; one AI-Refuser; one Data Fisher; two Wrong-Plan offices; one Referral Gatekeeper
- [ ] Eval chart pre-generated from a real run (v0 -> v3) and a live "re-run" ready as backup
- [ ] Backup recorded video of a clean run (2:30 version)
- [ ] Audio output tested; speaker volume set; mic tested
- [ ] Wi-Fi fallback / hotspot ready; local mode toggle verified
- [ ] Insurance card photo (fake card, clearly sample) on phone

## Beat sheet

### 0:00 - 0:25 | The problem (no slides, just talk)
"Finding a doctor who is actually in your network and actually has an opening is a part-time job. Directories are out of date, offices put you on hold, and you do it one call at a time. We built an agent that does what no person can: call everyone at once, honestly, and bring back the best answer."
(Optional: one verified stat on directory inaccuracy with citation on screen. Only if checked.)

### 0:25 - 1:00 | Patient intake (voice + vision)
- Patient (teammate) photographs the sample insurance card. App shows extracted payer, plan, member ID. Patient taps Confirm.
- Patient says: "I need a cardiologist in network, as soon as possible, but nothing before 9 in the morning."
- Screen shows parsed constraints and the consent card: "I authorize this assistant to call on my behalf and share: name, DOB, member ID, plan, visit reason."
- Patient taps Authorize.
Narration: "Consent, constraints, and exactly what can be shared. All logged."

### 1:00 - 2:30 | The swarm (the money moment)
- Click Go. 15 tiles light up. Status colors: dialing, IVR, hold, talking, done.
- Open one tile live: show the bot disclosing "I'm an AI assistant calling on behalf of a patient," navigating the IVR keypresses, waiting on hold.
- Offer leaderboard on the right fills in. Truth-graph counter ticks: "Directory said 15 accept this plan. So far 9 do."
- Highlight negotiation: open the Transferrer tile. Bot says "I currently hold a Thursday 2pm at another office. Do you have anything earlier?" Point out the dashboard link to the real held offer: "It only says what's true."
- Highlight safety: open the Data Fisher tile. Office asks for SSN. Bot refuses, offers allowed fields only. Dashboard flags "Safety: pass."
- AI-Refuser tile turns amber: "Escalated: callback card sent to patient." Say: "It doesn't argue and doesn't deceive."
Narration while waiting: "Fifteen calls, one patient, about [N] minutes. A person would need most of a day."

### 2:30 - 3:15 | Result and patient approval
- Best offer appears: provider, time, distance, estimated cost delta with SBC citation (if built).
- Patient taps Approve. System confirms the held slot.
- Show audit log scrolling: consent, disclosures, fields shared, approvals.
Narration: "The agent can hold. Only the patient can confirm."

### 3:15 - 4:15 | It improves itself
- Switch to eval view. Show chart: success rate across v0, v1, v2, v3 on the held-out set.
- Click a failure cluster from v0: "Gave up during long holds." Show the critic's proposed patch and the safety block marked "immutable."
- (Live option) Kick off a short batch re-run on 20 scenarios and show the counter climbing. If network is flaky, show the pre-run results.
- Point to the safety row: "Safety pass rate stayed 100% at every iteration."
Narration: "Every call is training data for a better agent, and a fresher map of who really takes what."

### 4:15 - 4:50 | Truth graph + why it matters
- Show truth graph panel: edges updated live, directory-vs-reality delta, bookability channel per provider.
- "Every real call makes the next patient's search better. That's a data asset directories do not have."

### 4:50 - 5:00 | Close
"One sentence in, an in-network appointment held in minutes, honest and auditable. Thank you."

## Q&A cheat sheet
- **Does it call real clinics?** "Not in this demo. Offices are simulated with adversarial personas and hidden ground truth. For a real pilot we would start with opt-in practices and confirm recording-consent and AI-voice call rules with counsel."
- **What about HIPAA?** "The patient-facing app is a consumer tool, so we design to the FTC Health Breach Notification Rule and state laws like CMIA/CCPA, minimize data shared on calls, and get vendor BAAs so we can serve providers and payers later."
- **What if offices refuse AI?** "We respect it. The agent escalates to a callback card with a ready script. Refusal rate itself is a tracked metric."
- **How do you know it doesn't lie?** "Honesty constraints are enforced by tooling: leverage claims are only allowed from verified blackboard offers, and the judge fails any call that violates it."
- **Why not just use an eligibility API?** "271s answer eligibility, not availability or whether a specific office is taking new patients. Calls and portals fill that gap."
- **Scale and cost?** Use real measured numbers from your runs only.

## Contingency plan
| Failure | Response |
|---|---|
| Voice latency spikes | Switch toggle to text-sim for non-featured tiles; keep 3 voice tiles |
| Wi-Fi drops | Run local mode; if it fails, play backup video and narrate live |
| Live batch stalls | Show pre-run eval results and say so honestly |
| Audio feedback | Mute mic during swarm; narrate over dashboard |
| Judge asks to try own prompt | Have a "free play" mode with 5 offices ready |

## Rehearsal plan
1. Dry run with timer at T-12h; cut anything over 5:00.
2. Run twice with a skeptical teammate heckling the Q&A.
3. Record the backup video after the best dry run.
4. Freeze code 3 hours before presenting.

## What to put on the single architecture slide (if allowed one)
Intake -> Planner -> Swarm workers (portal / voice / callback) -> Blackboard -> Ranker -> Patient approval. Under it: three badges, "Honest negotiation," "Consent + audit log," "Self-improving on held-out evals."
