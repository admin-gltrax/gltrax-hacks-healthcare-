# Demo day: 3-minute pitch and app overview

> **Keep this current.** Update this file in the same pull request as any user-visible feature, and re-time it out loud before submission (due **Nov 4, 9:00 PM ET**). The checklist at the bottom says what each beat depends on. Last updated: Oct 29, 2026 (adversarial reviewer, call gym, judges, reader eval on partner credits).

**Live app:** https://swarm-scheduler.72q91gp7bkhmc.us-west-2.cs.amazonlightsail.com/ (click "Or explore a demo patient"). All people, plans, offices and agencies on screen are fictional.

**Target:** about 420 spoken words at 150 words a minute, plus pauses for clicks.

---

## The script

### 0:00 – 0:20 · The problem
**Say:**
"Healthcare is built for the doctor's office, not for you. The benefits you already pay for are buried. Bills are wrong. Denials take weeks of calls. And most of that work lands on families: 53 million Americans are unpaid caregivers, many of them adult kids on hold for a parent."

**Screen:** the welcome page, PJ the Gila monster.

### 0:20 – 0:40 · The product
**Say:**
"This is PJ Health. It puts the power back in the patient's hands. You tell PJ what you need, and PJ's crew of AI agents does the complicated part: the calls, the forms, the appeals and the follow-ups. You just decide and sign."

**Click:** "Or explore a demo patient". The home screen opens on **What should PJ do?**, a menu of actions, not a chat box.

### 0:40 – 1:05 · Caring for Mom
**Say:**
"Alex is caring for their mom, Rosa. She's 78, on Medicare Advantage, lives alone, and fell this spring. Rosa gave Alex power of attorney, so Alex can act and sign for her. For Alex's son Leo, a parent manages it automatically until he turns 18. And another adult sees nothing until they say yes."

**Click:** the **Rosa** chip. Point at the consent banner.

### 1:05 – 1:25 · Benefits she's not using
**Say:**
"From her age, her plan and what Alex told it, PJ found nine benefits Rosa isn't using: the free Wellness Visit, a fall-risk check, a free medication review, rides her plan already covers, and help paying for Medicare. One tap each: 'Do it, PJ.'"

**Click:** "Find benefits Rosa isn't using", then **Do it, PJ** on the rides.

### 1:25 – 1:55 · The crew fights back, live on Meta's models
**Say:**
"Her plan denied home physical therapy after the fall. Alex just snaps a photo of the letter. Muse Spark reads it: the reason, word for word, the plan's four rules, and the real deadline. Spark calls her doctor's office for a letter. Muse Wonder lines up her records against each rule. Spark writes the appeal. Then open-weights Muse Spark plays the insurer and tries to deny it; Spark revises, or PJ lists what's missing. Nothing leaves until Alex signs."

**Click:** **Appeal a prior-authorization denial** → **Use the sample (fictional)** → **Start**. Steps light up with **Muse Spark** / **Muse Wonder** / **Muse Spark Open** badges; open **The plan's rules, answered one by one**, then **Stress test** (the reviewer's objections and the revision), then **Guardrails**. Type "Alex Rivera", **Sign and send**. (Takes about 45 s live; cut the wait in the edit.)

### 1:55 – 2:15 · A no is not the end
**Say:**
"If the plan says no again, PJ doesn't stop. It prepares the independent outside review, and watches every deadline."

**Click:** **They say no** (demo control). The outside-review workflow appears, waiting for a signature.

### 2:15 – 2:25 · PJ calls the doctor's office
**Say:**
"That letter? Spark phoned the office: worked the menu, waited on hold, got transferred to the medical assistant, said up front it's an AI, refused when the front desk asked for her home address, and came back with a reference number that code checks was really said on the call. We tested it on 600 hostile simulated offices: 100% safe."

**Click:** expand the call on the appeal (it streams live while it happens). Optional cut: `/gym`, the proving ground, one call per persona.

### 2:25 – 2:40 · The swarm
**Say:**
"Need an appointment? PJ checks the real public directories first: UnitedHealthcare's lists 251 Phoenix cardiologists in network. Then it calls 15 offices at once and holds the best slot for a yes. That run is live on Meta's Muse Spark: 15 calls in about 25 seconds."

**Click:** **Hold an appointment: call 15 offices at once**, then **Replay recorded run**.

### 2:40 – 3:00 · Why us, why now
**Say:**
"Same crew for a wrong bill (Spark reads the bill and the EOB, code does the math: $493 overcharge), rides, oxygen, cut home care hours, and a counselor who can actually see you. Ask PJ anything; crisis words get 988 before any model sees them. Muse Spark and Muse Wonder, real provider directories, consent gates, a 20-case red team at 100% live, a 600-call gym at 100% safe, and 152 tests. PJ Health: your healthcare, owned by you."

**Screen:** the action menu, then PJ.

---

## If they ask (one line each)

| Question | Answer |
|---|---|
| Does it call real offices? | Not in the demo: the offices, plans and agencies are simulated and labeled, and there's no phone line attached on purpose. The swarm's caller is a real Muse Spark agent with phone tools (keypad, hold, transfer); a telephony channel plugs in behind the same interface the fax uses. The provider directory data is real public data, and nobody is ever called with it. |
| What's AI vs rules today? | Live on Meta: the swarm's calls and the doctor's-office caller (Spark), reading letters, bills and EOBs (Spark vision, 25/25 fields on our eval), the appeal strategy (Wonder), the letters and PJ's chat (Spark). Rules are the guardrails and the fallback: deadlines, money math, consent, crisis routing. The screen badges every step with the engine that did it. |
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
| 0:40 | Care circle with consent levels | `src/agents/circle.py` | ✅ |
| 1:05 | Support plan from risk factors | `src/agents/outreach.py` | ✅ |
| 1:25 | Appeal from a photo: Spark reader → Spark caller → Wonder evidence map → Spark writer → checks → signature | `reader.py`, `office_caller.py`, `appeals.py`, `workflows.py` | ✅ live on Meta models |
| 1:55 | Escalation to outside review | `workflows._escalate` | ✅ |
| 2:15 | Doctor's-office call on Spark: menu, hold, transfer, data-fishing refused, reference verified | `src/agents/office_caller.py`, `src/sim/pcp_office.py` | ✅ live agents, simulated office |
| 2:25 | Real directory step, then the 15-call swarm on Muse Spark | `src/swarm/candidates.py`, `/swarm` | ✅ (the replay predates the directory step; re-record before demo day) |
| 2:40 | Other crew jobs: equipment, rides and aide, home care hours, counselor | `src/agents/workflows.py` | ✅ |
| 2:40 | Bill + EOB photos, code math, $493 overcharge | `reader.match_bill` | ✅ live |
| 1:25 | Stress test: Muse Spark Open tries to deny the appeal; Spark revises; leftover gaps become to-dos | `src/agents/reviewer.py`, `workflows._pa_review` | ✅ live (reviewer on Baseten, `muse-spark-open-1026`) |
| 2:15 | Call gym, judges, reader eval, voice loop at `/gym` | `src/sim/gym.py`, `src/eval/`, `gym.html` | ✅ live runs committed; voice audio plays only with `VOICE_TTS` on |
| any | Ask PJ on Spark (proposes jobs as cards) and voice intake | `guide.ask_live`, `src/voice.py` | ✅ chat live (red team 20/20); voice on `/swarm` only |

**Before recording:**
1. Re-record the public replay (`scripts/make_recording.py`) so it includes the directory step and the UHC plan.
2. Deploy `main` and run through the clicks on a phone.
3. Re-time the script: it's about 475 spoken words, over the 420 target. Cut the 1:55 beat first, then the 2:15 call beat.
