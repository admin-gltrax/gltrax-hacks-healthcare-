# Demo day: 3-minute pitch and app overview

> **Keep this current.** Update this file in the same pull request as any user-visible feature, and re-time it out loud before submission (due **Nov 4, 9:00 PM ET**). The checklist at the bottom says what each beat depends on. Last updated: Oct 29, 2026.

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

### 1:25 – 1:55 · The crew fights back
**Say:**
"PJ's crew already won one: a bill charged the same visit twice. PJ pulled the itemized bill, matched it to the plan's EOB, and saved $433. Now, a denial. Her plan refused home physical therapy after the fall. Six agents read the denial and the deadline, pulled her records, got her doctor's letter, and wrote the appeal. Nothing leaves until Alex reads it and signs."

**Click:** scroll to **PJ's crew is working on**. Show the steps and agent names, type "Alex Rivera", then **Sign and send**.

### 1:55 – 2:15 · A no is not the end
**Say:**
"If the plan says no again, PJ doesn't stop. It prepares the independent outside review, and watches every deadline."

**Click:** **They say no** (demo control). The outside-review workflow appears, waiting for a signature.

### 2:15 – 2:25 · PJ calls the doctor's office
**Say:**
"The appeal needed a letter from Rosa's doctor, so PJ called the office: pressed 0, waited on hold, got transferred to the doctor's medical assistant, said up front it's an AI calling with Rosa's permission, shared only her name, birthday and member ID, and came back with a reference number. Alex never sat on hold."

**Click:** open **Calls PJ made** on the appeal and expand the transcript.

### 2:25 – 2:40 · The swarm
**Say:**
"Need an appointment? PJ checks the real public directories first: UnitedHealthcare's lists 251 Phoenix cardiologists in network. Then it calls 15 offices at once and holds the best slot for a yes. That run is live on Meta's Muse Spark: 15 calls in about 25 seconds."

**Click:** **Hold an appointment: call 15 offices at once**, then **Replay recorded run**.

### 2:40 – 3:00 · Why us, why now
**Say:**
"Same crew for disputing a bill, renewing oxygen, getting rides or an aide, appealing cut home care hours, and finding a counselor who can actually see you. Built on the Meta Model API, with real provider directories, consent gates and 84 tests. PJ Health: your healthcare, owned by you."

**Screen:** the action menu, then PJ.

---

## If they ask (one line each)

| Question | Answer |
|---|---|
| Does it call real offices? | Not in the demo: the offices, plans and agencies are simulated and labeled, and there's no phone line attached on purpose. The swarm's caller is a real Muse Spark agent with phone tools (keypad, hold, transfer); a telephony channel plugs in behind the same interface the fax uses. The provider directory data is real public data, and nobody is ever called with it. |
| What's AI vs rules today? | The swarm's calls run on Muse Spark live, and voice intake on Muse Voice Transcribe. The patient-side crew runs on deterministic rules today; Spark vision for bills and denial letters, and Wonder for appeal plans, are next. |
| Safety? | PJ never diagnoses or doses. Crisis words get 988/911 first. Nothing is sent without a signature from someone allowed to sign. Every fact shows its source. Tests enforce all of these. |
| Who pays? | Families first (the caregiver pays, the parent uses it), then Medicare Advantage plans and employers, who want members using preventive benefits and fewer wasted appeals. |
| How is this different from Wellthy or Transcarent? | They give you a human coordinator or a benefits chatbot through your employer. PJ is a crew that acts for you, across every plan and agency, and you own the record. |
| Is it HIPAA compliant? | It's a demo with fictional data. The real path is identity verification, signed authorizations, a fax provider under a BAA, and real authentication; see `docs/FAMILY-AND-AGING.md`. |

## Feature checklist (keep in sync)

| Beat | Feature it shows | Where it lives | Status |
|---|---|---|---|
| 0:20 | Action-menu home screen | `src/agents/actions.py`, `home.html` | ✅ |
| 0:40 | Care circle with consent levels | `src/agents/circle.py` | ✅ |
| 1:05 | Support plan from risk factors | `src/agents/outreach.py` | ✅ |
| 1:25 | Bill dispute ($433 saved) and multi-agent prior-authorization appeal | `src/agents/workflows.py` | ✅ simulated counterparties |
| 1:55 | Escalation to outside review | `workflows._escalate` | ✅ |
| 2:15 | Doctor's-office call: phone menu, hold, transfer to the right person, reference number | `src/agents/office_calls.py`, `src/sim/pcp_office.py`, workflow `office_request` | ✅ simulated office |
| 2:25 | Real directory step, then the 15-call swarm on Muse Spark | `src/swarm/candidates.py`, `/swarm` | ✅ (the replay predates the directory step; re-record before demo day) |
| 2:40 | Other crew jobs: equipment, rides and aide, home care hours, counselor | `src/agents/workflows.py` | ✅ |
| any | Ask PJ chat and voice intake | `guide.py`, `src/voice.py` | ✅ chat (rules); voice on `/swarm` only |

**Before recording:**
1. Re-record the public replay (`scripts/make_recording.py`) so it includes the directory step and the UHC plan.
2. Deploy `main` and run through the clicks on a phone.
3. Re-time the script; cut the 1:55 beat first if over 3:00, then the 2:15 call beat.
