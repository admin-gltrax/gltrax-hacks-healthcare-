# Demo day: 3-minute pitch and app overview

> **Keep this current.** Update this file in the same pull request as any user-visible feature, and re-time it out loud before submission (due **Nov 4, 9:00 PM ET**). The checklist at the bottom says what each beat depends on. Last updated: Oct 30, 2026 (rewritten around the proving ground: call gym, judges, reader eval, stress test, claim checker).

**Live app:** https://swarm-scheduler.72q91gp7bkhmc.us-west-2.cs.amazonlightsail.com/ (click "Or explore a demo patient"). All people, plans, offices and agencies on screen are fictional.

**Target:** about 420 spoken words at 150 words a minute, plus pauses for clicks.

---

## The script

### 0:00 – 0:20 · The problem
**Say:**
"Healthcare is built for the doctor's office, not for you. Benefits are buried, bills are wrong, denials take weeks of calls, and the work lands on families: 53 million Americans are unpaid caregivers, many of them adult kids on hold for a parent."

**Screen:** the welcome page, PJ the Gila monster.

### 0:20 – 0:35 · The product
**Say:**
"This is PJ Health. You tell PJ what you need, and PJ's crew of AI agents does the calls, the forms, the appeals and the follow-ups. You just decide and sign."

**Click:** "Or explore a demo patient". The home screen opens on **What should PJ do?**, a menu of actions, not a chat box.

### 0:35 – 0:55 · Caring for Mom
**Say:**
"Alex cares for their mom, Rosa: 78, Medicare Advantage, lives alone, fell this spring. Rosa gave Alex power of attorney, so Alex can sign for her. PJ found nine benefits she isn't using, like rides her plan already covers. One tap: 'Do it, PJ.'"

**Click:** the **Rosa** chip (point at the consent banner), then **Find benefits Rosa isn't using** → **Do it, PJ** on the rides.

### 0:55 – 1:40 · The crew fights back
**Say:**
"Her plan denied home physical therapy. Alex snaps a photo of the letter. Muse Spark reads the reason, the plan's four rules and the real deadline, then phones her doctor's office for a letter: works the menu, waits on hold, says it's an AI, refuses to give out her address. Muse Wonder maps her records to each rule; Spark writes the appeal. Then the insurer goes first: open-weights Muse Spark plays the plan's reviewer and tries to deny it. Spark answers every objection, and a second model checks every claim against her records. What can't be fixed becomes a plain to-do. Nothing leaves until Alex signs, and if the plan still says no, PJ files the outside review."

**Click:** **Appeal a prior-authorization denial** → **Use the sample (fictional)** → **Start**. Steps light up with **Muse Spark** / **Muse Wonder** / **Muse Spark Open** badges. Open the call (it streams live), **The plan's rules, answered one by one**, **Stress test** (objections and the revision), then **Guardrails**. Type "Alex Rivera", **Sign and send**. About 60 s live; cut the wait in the edit. (The claim check shows under Guardrails only once the Modal endpoint is set; until then, drop "and a second model checks every claim against her records".)

### 1:40 – 2:15 · How we know it works
**Say:**
"Healthcare can't run on vibes, so we built a proving ground. Six hundred simulated hostile offices: data fishers, fake 'HIPAA verification', AI refusers, Spanish-first lines, voicemail. The caller stayed 100% safe and reached the right outcome every time. Two judges from different deployments agree at a kappa of about 0.85. The reader gets 99% of fields right from clean photos and 91% from bad ones. And every failure the gym or the judges found, we fixed and re-ran on fresh offices."

**Click:** `/gym`: the call-gym tiles, then **Listen in** on the *fake verification* persona.

### 2:15 – 2:35 · The swarm
**Say:**
"Need an appointment? PJ checks the real public directories, then calls 15 offices at once and holds the best slot for a yes: 15 live Muse Spark calls in about 25 seconds."

**Click:** **Hold an appointment: call 15 offices at once**, then **Replay recorded run**.

### 2:35 – 3:00 · Why us, why now
**Say:**
"Same crew for wrong bills, rides, equipment and cut home care hours. Crisis words get 988 before any model sees them. Everything that faces the patient runs on Meta's models; open weights play the adversary. Consent gates, a red team at 100%, 160 tests. PJ Health: your healthcare, owned by you."

**Screen:** the action menu, then PJ.

---

## If they ask (one line each)

| Question | Answer |
|---|---|
| Does it call real offices? | Not in the demo: the offices, plans and agencies are simulated and labeled, and there's no phone line attached on purpose. The swarm's caller is a real Muse Spark agent with phone tools (keypad, hold, transfer); a telephony channel plugs in behind the same interface the fax uses. The provider directory data is real public data, and nobody is ever called with it. |
| What's AI vs rules today? | Live on Meta: the swarm's calls and the doctor's-office caller (Spark), reading letters, bills and EOBs (Spark vision: 99.6% of fields on clean photos, 90.9% on harsh ones, across 33 fictional documents), the appeal strategy (Wonder), the letters and PJ's chat (Spark). Rules are the guardrails and the fallback: deadlines, money math, consent, crisis routing. The screen badges every step with the engine that did it. |
| Does it call real phones? | No: live Spark agents talk to simulated offices on purpose (TCPA, recording consent, and Meta has no text-to-speech). A phone channel plugs in behind the same interface as the fax. See `docs/COMPLIANCE.md`. |
| Safety? | PJ never diagnoses or doses. Crisis words get 988/911 first. Nothing is sent without a signature from someone allowed to sign. Every fact shows its source. Tests enforce all of these. |
| Who pays? | Families first (the caregiver pays, the parent uses it), then Medicare Advantage plans and employers, who want members using preventive benefits and fewer wasted appeals. |
| How is this different from Wellthy or Transcarent? | They give you a human coordinator or a benefits chatbot through your employer. PJ is a crew that acts for you, across every plan and agency, and you own the record. |
| How do you know it's safe at scale? | The call gym: 600 simulated offices across 16 kinds of trouble, every call scored in code (AI disclosed to each person, nothing beyond four fields shared, no human claim, nothing on voicemail, no made-up reference): 100%. Two judges from different deployments agree at kappa 0.84 to 0.87, and their disagreements go to a person. See `/gym` and `docs/evals.md`. |
| Why use other providers' models? | The rule: everything that faces the patient stays on Meta's Model API, enforced in code. Partner credits run Muse Spark Open, Meta's open weights, as the adversary (the insurer's reviewer), the simulated receptionists and the second judge. |
| Is it HIPAA compliant? | No claims: fictional data only. `docs/COMPLIANCE.md` lists what code enforces today and the ordered path to a pilot (real auth, verified POA and CMS-1696, BAAs, encryption, TCPA review). |

## Feature checklist (keep in sync)

| Beat | Feature it shows | Where it lives | Status |
|---|---|---|---|
| 0:20 | Action-menu home screen | `src/agents/actions.py`, `home.html` | ✅ |
| 0:35 | Care circle with consent levels | `src/agents/circle.py` | ✅ |
| 0:35 | Support plan from risk factors | `src/agents/outreach.py` | ✅ |
| 0:55 | Appeal from a photo: Spark reader → Spark caller → Wonder evidence map → Spark writer → checks → signature | `reader.py`, `office_caller.py`, `appeals.py`, `workflows.py` | ✅ live on Meta models |
| 0:55 | Escalation to outside review (said, not clicked) | `workflows._escalate` | ✅ |
| 0:55 | Doctor's-office call on Spark: menu, hold, transfer, data-fishing refused, reference verified | `src/agents/office_caller.py`, `src/sim/pcp_office.py` | ✅ live agents, simulated office |
| 0:55 | Stress test: Muse Spark Open tries to deny the appeal; Spark revises; leftover gaps become to-dos | `src/agents/reviewer.py`, `workflows._pa_review` | ✅ live (reviewer on Baseten, `muse-spark-open-1026`) |
| 0:55 | Claim checker: every claim in the letter needs a fact behind it (Qwen on Modal checks Spark's writing) | `src/agents/claims.py` | ✅ built; shows under Guardrails once the Modal endpoint is set |
| 1:40 | Call gym, judges, reader eval, voice loop at `/gym` | `src/sim/gym.py`, `src/eval/`, `gym.html` | ✅ live runs committed; voice audio plays only with `VOICE_TTS` on |
| 2:15 | Real directory step, then the 15-call swarm on Muse Spark | `src/swarm/candidates.py`, `/swarm` | ✅ (the replay predates the directory step; re-record before demo day) |
| 2:35 | Other crew jobs: equipment, rides and aide, home care hours, counselor | `src/agents/workflows.py` | ✅ |
| 2:35 | Bill + EOB photos, code math, $493 overcharge | `reader.match_bill` | ✅ live |
| any | Ask PJ on Spark (proposes jobs as cards) and voice intake | `guide.ask_live`, `src/voice.py` | ✅ chat live (red team 20/20); voice on `/swarm` only |

**Before recording:**
1. Re-record the public replay (`scripts/make_recording.py`) so it includes the directory step and the UHC plan.
2. Deploy `main` and run through the clicks on a phone.
3. Re-time the script out loud (about 400 spoken words). If over 3:00, cut the swarm beat to one sentence first.
