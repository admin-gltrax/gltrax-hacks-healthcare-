# PJ Health: healthcare built for the patient, not the doctor

> **Your healthcare, owned by you.** Healthcare is extremely complicated to navigate for the average person. PJ puts the power back in the patient's hands: it finds every benefit and resource they already have, and PJ's crew of AI agents does the complicated work so it's simple for the person using it. The calls, the forms, the appeals and the follow-ups are handled by the crew; the patient only decides and signs.
>
> PJ is a friendly Gila monster. The home screen is a menu of things PJ can do: call the doctor's office and get the right person, find benefits you aren't using, contest a wrong bill, appeal a denial, renew medical equipment, get rides or an aide, appeal cut home care hours, or call 15 offices at once to hold an appointment. It works for you, for an older parent, or for your child.

Built for the Meta Global AI Developer Hackathon (startup track) on the Meta Model API. **"PJ Health" is a working name** (see [Open questions](#16-open-questions)).

**Demo only.** Every patient, insurer, provider, phone number, fax number and record in this repo is fictional. No real clinic, insurer or fax machine is ever contacted. There is no password because no real health information may ever enter this build.

---

## Contents

1. [The pitch](#1-the-pitch)
2. [Quick start](#2-quick-start)
3. [What the patient sees](#3-what-the-patient-sees)
4. [The four buckets](#4-the-four-buckets)
5. [Onboarding: name, insurance, doctor, records](#5-onboarding-name-insurance-doctor-records)
6. [The agent crew](#6-the-agent-crew)
7. [Worked example: "I think I need to see a therapist"](#7-worked-example-i-think-i-need-to-see-a-therapist)
8. [Architecture](#8-architecture)
9. [Data model](#9-data-model)
10. [API](#10-api)
11. [Which Meta model does what](#11-which-meta-model-does-what)
12. [Demo build vs. the real product](#12-demo-build-vs-the-real-product)
13. [Safety and privacy rules](#13-safety-and-privacy-rules)
14. [Repo layout](#14-repo-layout)
15. [Build status and next steps](#15-build-status-and-next-steps)
16. [Open questions](#16-open-questions)

---

## 1. The pitch

Every patient portal today puts the provider first and the patient second. It shows what one health system has about you, in that system's words, and stops at that system's walls. Patients have no real way to run their own care:

- Insurance documents are unreadable, and the benefits people pay for go unused.
- Provider directories are wrong.
- Bills are wrong, denials take weeks of calls, and appeals have deadlines nobody explains.
- Records are scattered across offices that only answer by fax and keep you on hold.
- Most of this work lands on families: about 53 million Americans are unpaid caregivers.

### Philosophy

1. **Put the power in the patient's hands.** Use *all* of the benefits and resources they already have: plan benefits, the employer EAP, Medicare's free preventive care, rides and equipment the plan owes them, cost-help programs, community and state agencies.
2. **The AI does the complicated work so it's simple for the person.** The patient says what they want (or taps it); PJ's crew makes the calls, waits on hold, gets the right person, reads the bill, files the appeal, tracks the deadline, and escalates when the answer is no.
3. **Act, don't just inform.** The home screen is a menu of actions, not a dashboard or an empty chat box. Information and chat stay available, lower down.
4. **Proactive, from the person's own risk factors.** Age, plan and what the person or caregiver tells PJ (lives alone, a recent fall, many medicines, hard to afford...) become a support plan of covered next steps, each with the reason, the source and the cost. Never a diagnosis.
5. **Built for families.** Manage care for an older parent or a child, with consent rules that match real life and the law.
6. **The patient decides.** Nothing is sent without a signature from someone allowed to sign. Every fact shows its source.
7. **Push the frontier.** Incumbents give people a human to call (Wellthy, Cariloop) or a benefits chatbot through an employer (Transcarent/Accolade). PJ is a crew that acts for the person across every plan, office and agency. See [docs/FAMILY-AND-AGING.md](docs/FAMILY-AND-AGING.md).

Messaging: **"Healthcare built for the patient, not built for the doctor."** / **"Your healthcare, owned by you."**

The 3-minute demo-day script lives in [docs/DEMO-PITCH.md](docs/DEMO-PITCH.md) and is kept current with every feature.

## 2. Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

MOCK_LLM=1 pytest -q                                   # 63 tests, offline, no key
MOCK_LLM=1 uvicorn src.api.server:app --port 8000      # http://localhost:8000
```

**Pages**

- `http://localhost:8000/` is the **patient dashboard**. Type a first name to start, or click **Explore a demo patient** to see everything filled in.
- `http://localhost:8000/swarm` is the **Scheduling Swarm** dashboard: 15 simulated calls, the real provider-directory tab, and voice intake. Add `?debug=1` to show each office's hidden persona.

**Live demo:** https://swarm-scheduler.72q91gp7bkhmc.us-west-2.cs.amazonlightsail.com/ (AWS Lightsail; see [DEPLOY.md](DEPLOY.md)).

**Demo insurance cards (all fictional)**

| Card | Plan |
|---|---|
| `EVG-55120943` | Employer PPO. Includes an EAP if the employer is "Northwind Logistics". |
| `BWM-77031882` | Medicare Advantage HMO. Referrals required. |
| `PSM-30018467` | Medicaid managed care. |

**Try this:** search for the PCP **"Harbor"**. The directory has a stale fax number and a stale network status for that office, and PJ's verification call catches both.

**With the real Meta Model API:**

1. Run `cp .env.example .env`.
2. Add `MODEL_API_KEY` to `.env`.
3. Run `python scripts/smoke_meta.py`. Every line should say PASS.

Hosting is covered in [DEPLOY.md](DEPLOY.md). For swarm evals, see [docs/swarm-architecture.md](docs/swarm-architecture.md) and run `python -m src.eval.run_batch`.

## 3. What the patient sees

Everything is on one page (`src/api/static/home.html`). From top to bottom:

| Part | What it does |
|---|---|
| **Welcome** | The patient enters a name (email optional, no password) or clicks "Explore a demo patient". |
| **Greeting and PJ** | PJ says what's next, or what needs a signature. |
| **Whose care** | Chips for you and everyone in your care circle (an older parent, a child), plus "Add someone". A banner shows how access was granted (parent of a minor, the person said yes, or power of attorney). |
| **What should PJ do?** | The action menu: find a doctor who really takes the plan, have PJ call the doctor's office, find benefits not used yet, what the plan covers, get records, book a checkup or Wellness Visit, tell PJ about yourself, manage care for a parent or child. |
| **PJ's crew jobs** | "Get care" (the scheduling swarm, finding a counselor), "Fight a wrong bill or a no" (bill dispute, prior-authorization appeal, home care hours appeal), "Get what the plan owes you" (rides, aide, supplies, medical equipment). |
| **PJ's crew is working on** | Each workflow's steps and agents, findings, call logs (menu, hold time, who PJ reached, reference number, transcript), deadlines, the full letter before signing, the outcome and money saved. |
| **Benefits and support PJ found** | The support plan from age, plan and risk factors, with "Do it, PJ" and "Not now". |
| **Or just say it** | The Ask PJ chat (also the floating button). Ranked care options with a "Do it, PJ" button. |
| **Four buckets** | Life & Connection, Clinicals, Routines, Family & Genes ([section 4](#4-the-four-buckets)). |
| **Side panels** | What PJ is doing for you, My Coverage, My Care Team, Records requests. |
| **Footer** | Crisis notice (988 / 911), demo disclaimer, and a link to the swarm. |

Design rules:

- Plain language, at about a 6th-grade reading level.
- Every number comes with "what this means".
- Every fact shows its source and how sure PJ is.
- Mobile first. Tested at iPhone width with no horizontal scrolling.

## 4. The four buckets

The buckets are defined in `src/patient/buckets.py`. The screen uses plain names. The clinical term is kept for clinicians and for mapping to standards.

| Bucket (on screen) | What goes in it | Clinical term | Where the data comes from |
|---|---|---|---|
| **Life & Connection** | Who you live with, who helps you, caregiving, transport, food, housing, money stress, loneliness | Social determinants of health (SDOH) | The patient (short check-ins), screening answers in records, plan benefits such as rides |
| **Clinicals** | Lab results, vitals, conditions, medicines, allergies, shots, visits | Clinical data (problems, meds, allergies, labs, immunizations, encounters) | Records requests, the payer Patient Access API, and later lab and pharmacy feeds |
| **Routines** | Food, sleep, movement, stress, alcohol and tobacco, screen time | Lifestyle and behavioral factors | The patient, and later wearables |
| **Family & Genes** | Family history, genetic tests, things to watch for because of them | Family history, genetic risk | The patient, records, genetic test reports |

Every item is a `HealthItem`. Each one has:

- A flag: **ok**, **watch** ("keep an eye on it") or **act** ("worth doing something about").
- A `plain_meaning`.
- A `source` and a `confidence`.

Flags are informational ("ask your doctor about..."). They are never diagnoses.

Coverage, care team and PJ's task list appear as panels rather than buckets. They are the logistics around your health, not your health itself.

## 5. Onboarding: name, insurance, doctor, records

The patient does four small things, and each one sets off agent work.

| Patient does | PJ and the crew do | Result on the dashboard |
|---|---|---|
| 1. Types a name | Create a record and a session cookie. | "Hi Sam, I'm PJ..." |
| 2. Enters the insurance card (and employer) | **Coverage agent:** read the card, log into the insurer portal, collect benefits, the deductible and referral and authorization rules, write a plain summary, and check for an employer EAP. | My Coverage is filled in, in plain words, including any EAP found through the employer. |
| 3. Names their doctor | **Care Team agent:** search the directory, then **call** the office to confirm the fax number and network status (directories are often wrong), and correct the record. | The PCP appears with a **confirmed** fax and network status, for example: "Good thing I called: the fax in the directory was stale." |
| 4. Types their name to sign | **Records agent:** write the right-of-access letter, fax it to the confirmed number, track the 30-day clock, follow up, and file what comes back into the buckets. | The records request shows "sent, due by <date>". When the office answers, results fill the buckets. |

`Patient.onboarding_step` moves through `welcome → coverage → pcp → records → done`. `guide.next_step()` turns the current step into what PJ says.

**Why the call in step 3 matters:** in the real world, a records request sent to a stale directory fax fails silently. In the simulation, `SimulatedFax` delivers only to an office's true fax number. The test `test_stale_fax_fails_until_verified` proves that the verification step does real work.

## 6. The agent crew

PJ is the only voice the patient hears. PJ hands work to specialist agents. Each agent writes back `AgentTask` updates, so the dashboard always shows what's happening.

| Agent | File | Job |
|---|---|---|
| **PJ (guide)** | `src/agents/guide.py` | Says what's next, explains things, routes requests. Never diagnoses. |
| **Coverage** | `src/agents/coverage.py` | Reads the card, gets benefits, writes the plain summary, finds the EAP. |
| **Care Team** | `src/agents/care_team.py` | Finds the PCP and others. Confirms phone, fax, network status and whether they're accepting new patients. |
| **Records** | `src/agents/records.py` | Writes the right-of-access letter, collects the signature, faxes it, tracks the 30-day clock, follows up and files the results. |
| **Care Navigator** | `src/agents/navigator.py` | Turns "I need X" into ranked pathways with costs. |
| **Scheduling Swarm** | `src/swarm/`, `src/agents/worker.py` | Calls many offices at once to find and hold a real in-network slot. |
| **Caller** | `src/agents/office_calls.py` | Calls the patient's doctor's office for anything: works the phone menu, waits on hold, gets transferred to the right person, and logs who it spoke with and the reference number. |
| **Outreach** | `src/agents/outreach.py` | Turns age, plan and risk factors into a support plan of covered next steps. Never diagnoses. |
| **Care circle** | `src/agents/circle.py` | Consent and permissions for acting on behalf of an older parent, a child or a spouse. |
| **Workflow crew** | `src/agents/workflows.py` | Runs multi-agent jobs end to end: bill dispute, prior-authorization appeal (and outside review), rides/aide/supplies, medical equipment, home care hours appeal, counselor request, doctor's-office requests. |

How each agent works today, and what it becomes:

| Agent | Hackathon build | Real product |
|---|---|---|
| **PJ (guide)** | Deterministic routing and copy. | Muse Spark grounded on the patient's own record, with an immutable safety block like the one in `src/safety.py`. |
| **Coverage** | Simulated insurer portal (`src/sim/payers.py`). | The payer Patient Access API (FHIR) through an aggregator, plus X12 270/271 eligibility checks. Computer-use on the insurer portal only as a fallback. |
| **Care Team** | Simulated directory with planted errors (`src/sim/providers.py`). | The NPPES NPI registry and payer FHIR provider directories, followed by a verification call. The swarm already uses real NPPES and Plan-Net data (`src/directory/`). |
| **Records** | `SimulatedFax` and a simulated records office. | A HIPAA-eligible fax API covered by a business associate agreement (BAA), e-signature, and OCR plus Muse Spark extraction of returned records into `HealthItem`s. |
| **Care Navigator** | Rules over the patient's coverage and the true directory data. | Muse Wonder plans, Muse Spark explains, using real benefit and directory data. |
| **Scheduling Swarm** | Built: 15 parallel simulated calls, honest leverage, holds only. | Real telephony in a post-hackathon pilot. The patient confirms every booking. |

Planned agents (not built yet):

- **Meds:** tracks refill timing and finds cheaper options on the plan's formulary (refill requests already go through the Caller).
- **Check-ins:** asks short Life & Connection and Routines questions over time.

## 7. Worked example: "I think I need to see a therapist"

The patient types only that sentence. `navigator.navigate()` does the rest:

1. **Check for a crisis first.** If the text contains crisis words, the top option is always 988 / 911 (`test_crisis_always_first`).
2. **Classify the need** (`navigator.classify`): therapy, psychiatry, dermatology, physical therapy, primary care, and so on. "Physical therapy" is never confused with talk therapy.
3. **Check every route the patient might have**, using their actual coverage:
   - **EAP:** free sessions through the employer, if there is one (`EMPLOYER_EAP`).
   - **In network:** therapists who are *truly* in network and accepting new patients. PJ also names directory listings to skip, such as a practice the directory lists that isn't taking new patients.
   - **PCP first:** when the plan requires a referral (HMO, Medicare Advantage HMO).
   - **Video visit** through the plan.
   - **Medicare** or **Medicaid** routes when the plan is one of these. For Medicaid this includes the plan's behavioral health line and rides to appointments.
   - **Community:** 211, sliding-scale clinics, community mental health centers.
   - **Self-pay**, if the patient is uninsured.
4. **Rank the options** by cost, speed and fit, and recommend one. Each option says in plain words what it costs, why it fits, the steps, and what PJ can do for you.
5. **The patient picks one, and PJ does it** (`POST /api/p/care/{id}/go`).
   - **Today:** this records a working task. The agent is `swarm` for the in-network option.
   - **Next:** run the swarm for in-network, request the referral for PCP-first, and start the EAP intake call.

The same machinery handles other requests:

- "I need a dermatologist for a mole" (HMO, so a PCP referral comes first).
- "I need physical therapy for my knee."
- "I need a new primary care doctor."

## 8. Architecture

```
┌────────────────────────── Browser (home.html, vanilla JS) ──────────────────────────┐
│ Welcome · PJ bar + Ask · setup cards · 4 buckets · tasks · coverage · care team     │
└──────────────────────────────────────────┬───────────────────────────────────────────┘
                                           │ fetch, cookie pj_session
┌──────────────────────────────────────────▼───────────────────────────────────────────┐
│ FastAPI  src/api/server.py   /   /swarm   /api/p/* (src/api/patient.py)   /api/swarm │
└──────┬─────────────┬──────────────┬───────────────┬──────────────┬───────────────────┘
       │             │              │               │              │
┌──────▼─────┐ ┌─────▼────┐ ┌───────▼────┐ ┌────────▼───┐ ┌────────▼───────┐
│ PJ guide   │ │ Coverage │ │ Care Team  │ │ Records    │ │ Care Navigator │
└──────┬─────┘ └─────┬────┘ └───────┬────┘ └────────┬───┘ └────────┬───────┘
       │             │              │               │              │ "Do it, PJ"
       │             │              │               │     ┌────────▼─────────┐
       │             │              │               │     │ Scheduling Swarm │
       │             │              │               │     └────────┬─────────┘
┌──────▼─────────────▼──────────────▼───────────────▼──────────────▼───────────────────┐
│ Adapters (today: simulated)                                                           │
│ sim/payers.py (insurer portal) · sim/providers.py (directory vs truth)                │
│ channels/fax.py (SimulatedFax) · sim/records_office.py · sim/ offices (swarm calls)   │
└───────────────────────────────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ Store: src/patient/store.py (in memory; optional JSON files via PATIENT_STORE_DIR)    │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

Principles:

- **Everything goes through an adapter.** Each agent talks to a payer, directory, fax or phone interface. The hackathon build wires in simulated ones, and production swaps in real ones without touching the agents. `FaxChannel` in `src/channels/fax.py` is the pattern to copy.
- **Every fact carries a `source` and a `confidence`.** Confidence goes from `unverified` (the directory said so) to `likely` to `confirmed` (PJ called, or the insurer or the records say so).
- **The patient approves anything that leaves the building.**
  - A records request needs a typed signature (`NotSigned`).
  - A booking needs the patient's yes. The swarm only holds slots.
- **Each patient has one record (`HealthRecord`)**, which can be exported as JSON at any time (`GET /api/p/me/export`).

## 9. Data model

The models are in `src/patient/models.py` (pydantic v2).

| Model | Key fields |
|---|---|
| `Patient` | display_name, email?, dob?, zip_code?, employer?, onboarding_step |
| `Coverage` | payer, plan_name, plan_type, member_id, `program` (employer / marketplace / medicare / medicare_advantage / medicaid / dual / none / unknown), deductible and out-of-pocket maximum (and how much of each is met), pcp_required, EAP, phone lines, `benefits: [BenefitLine]`, plain_summary |
| `BenefitLine` | service, label, covered, you_pay, needs_referral, needs_prior_auth, visit_limit, notes |
| `CareTeamMember` | role, name, practice, specialty, npi, phone, fax, address, in_network (yes / no / unknown), source, confidence |
| `RecordsRequest` | to, what, date_range, delivery, letter, signed_at, sent_at, due_by, fax_id, history, status (draft → awaiting_signature → sent → acknowledged → received, or overdue / failed) |
| `HealthItem` | bucket, kind, title, value, when, plain_meaning, flag (ok / watch / act), source, confidence |
| `AgentTask` | title, agent (coverage / care_team / records / navigator / swarm / guide), status (todo / working / waiting_on_you / waiting_on_them / done / blocked), detail, needs_you |
| `CareRequest` | need_text, need, urgent, `pathways: [Pathway]`, recommended |
| `Pathway` | kind (crisis / eap / in_network / pcp_first / telehealth / medicare / medicaid / community / self_pay), title, why, cost, steps, agent_can_do, rank |
| `HealthRecord` | patient, coverage, care_team, items, records_requests, tasks, care_requests |

How these map to standards in the real product:

| Our model | Standard |
|---|---|
| `HealthItem` | FHIR Observation, Condition, MedicationStatement, AllergyIntolerance, Immunization, FamilyMemberHistory |
| `Coverage` | FHIR Coverage, plus the X12 271 eligibility response |
| `CareTeamMember` | FHIR Practitioner and PractitionerRole (Plan-Net) |
| Life & Connection items | Gravity Project SDOH codes |

## 10. API

All patient routes are under `/api/p`. The session is the `pj_session` cookie (HTTP-only, SameSite=Lax). Every response returns the full dashboard: patient, PJ's line, buckets, panels, coverage, care team, records requests, tasks and recent care requests.

| Method and path | Body | What it does |
|---|---|---|
| `POST /start` | `{name, email?}` | Create a record (name only, demo). |
| `POST /demo` | | Load a fully set-up fictional patient. |
| `POST /signout` | | Clear the cookie. |
| `GET /me` | | Return the dashboard. |
| `GET /me/export` | | Return everything as JSON. |
| `POST /coverage` | `{card, employer?}` | Run the Coverage agent. Returns 404 if the plan isn't found. |
| `GET /providers?q=` | | Search the directory. |
| `POST /pcp` | `{sim_id}` | Add the PCP and verify it by "calling". Returns `corrections`. |
| `POST /records` | | Draft the records request. Returns `request_id`. |
| `POST /records/{id}/sign` | `{typed_name}` | Sign (the name must match the patient's) and fax. |
| `POST /records/{id}/simulate-response` | | Demo control: the office answers. |
| `POST /ask` | `{text}` | Ask PJ. Returns `answer` of type `care_request`, `coverage` or `chat`. |
| `POST /care/{care_id}/go?kind=` | | The patient picks a pathway, and PJ starts it. |
| `POST /circle` | `{name, relation, dob?}` | Add someone to the care circle (a minor: parent access; an adult: nothing until they say yes). |
| `POST /circle/{id}/consent` | `{typed_name, permissions}` | The person says yes, typing their own name, and picks view and/or act. |
| `POST /circle/{id}/representative` | `{typed_name, document}` | The account holder attests to healthcare power of attorney or guardianship. |
| `DELETE /circle/{id}` | | Remove someone. |
| `POST /active` | `{person_id}` | Switch whose care the dashboard shows (`null` = yourself). |
| `POST /about` | `{factors, dob?, employer?}` | What the person told PJ (risk factors). |
| `POST /support/{key}/go`, `/dismiss` | | Start or dismiss a support-plan suggestion. |
| `POST /workflows` | `{template, inputs}` | Start a crew job. Runs every agent step up to the consent gate. |
| `POST /workflows/{id}/approve` | `{typed_name}` | Sign; then PJ sends and starts the clock. |
| `POST /workflows/{id}/simulate-response?outcome=` | | Demo control: the other side answers (`approved` or `denied`; a denial escalates). |

Every route works on the person currently being viewed, and checks the account holder's permission for them: `view`, `act` (start work) or `approve` (sign). A failed check returns 403 with a plain explanation.

The swarm keeps its existing routes: `POST /api/swarm/start`, `POST /api/approve`, `POST /api/replay`, `GET /api/events` (SSE), `GET /api/state` and `GET /api/config`. See [docs/swarm-architecture.md](docs/swarm-architecture.md).

## 11. Which Meta model does what

| Job | Model | Notes |
|---|---|---|
| PJ's voice: explanations and answers grounded on the patient's record | `muse-spark-1.3` | Uses an immutable safety block and retrieval over `HealthItem`s and `Coverage`. |
| Reading an insurance card photo, a lab report or a returned records PDF | `muse-spark-1.3` (vision) | Produces structured output into `Coverage` and `HealthItem`. |
| Planning care pathways, multi-step coordination, chasing late records | `muse-wonder-1.0` | Agentic and long horizon. Use sparingly because of cost. |
| Logging into a simulated insurer portal to read benefits | Meta computer-use | **Simulated portal only** in the hackathon. Real portals use APIs, and passwords are never stored. |
| Scheduling Swarm calls | `muse-spark-1.3` workers, with Wonder as planner and critic | The existing build. |
| Patient talks instead of typing | `muse-voice-transcribe-1.0` | Already used for the swarm's voice intake (`src/voice.py`, file transcription). Meta has no text-to-speech, so PJ replies on screen. |
| PJ illustrations and plain-language visuals | `muse-image-1.0` | Fixed character art for PJ. No patient data goes into prompts. |

Hard rule: **no real PHI goes to any model in this build, and nothing ever goes to `-contributor` models** (Meta trains on those prompts). All demo data is fictional.

## 12. Demo build vs. the real product

| Piece | Hackathon (now) | Real product (later) |
|---|---|---|
| Sign-in | Name only, a random session cookie, an in-memory store. | Real authentication (passkeys, or an email magic link plus MFA), identity proofing before pulling records, and encrypted per-patient storage. |
| Insurance | Fictional insurers, keyed by member-ID prefix. | The payer **Patient Access API** (FHIR; CMS rules require it for many public-program payers) through an aggregator, plus **X12 270/271** eligibility checks through a clearinghouse. The patient authorizes with the insurer's own login (OAuth). **PJ never stores portal passwords.** |
| Finding the doctor | A fictional directory with planted errors. | The **NPPES** NPI registry and payer **Plan-Net** FHIR directories, followed by a verification call. Keep a "directory vs reality" dataset. |
| Records | A signed letter, `SimulatedFax`, and an instant demo response. | HIPAA right of access (45 CFR 164.524: 30 days, with one 30-day extension) [from memory: verify]. A fax API that signs a **BAA**, patient e-signature, TEFCA and health information exchange queries where available, and OCR plus extraction. |
| Calls | Simulated offices (the swarm). | Real telephony for a pilot. PJ discloses that it is an AI assistant, and calls are recorded only with consent. |
| Hosting | One Docker container, a single instance. | A HIPAA-eligible cloud under a BAA, with audit logs, PHI-safe logging and backups. |

Do not claim HIPAA compliance. The honest claim is "designed to be compatible with HIPAA requirements; the demo uses fictional data only".

## 13. Safety and privacy rules

These rules apply to code, prompts and copy. Tests enforce the ones marked ✓.

1. **Crisis comes first.** Crisis words get 988 (call or text) and 911 before anything else. ✓
2. **PJ never diagnoses, gives doses, or tells anyone to start or stop a medicine.** Medical questions go to the patient's doctor or the plan's nurse line. ✓
3. **The patient decides.** PJ lays out the options and the patient chooses. Nothing leaves without consent:
   - Records requests need a typed signature. ✓
   - Bookings need the patient's yes; the swarm worker has no booking tool. ✓
4. **PJ says where every fact came from and how sure it is** (`source`, `confidence`).
5. **No passwords.** PJ never asks for or stores insurer or portal passwords.
6. **Data minimization.** Each agent gets only what its job needs. For example, the swarm worker gets name, DOB, member ID, plan, reason and constraints, and nothing more.
7. **Only fictional data goes in this repo.** No real names, employers, insurers, providers, or phone or fax numbers. Anything simulated is labeled as simulated.
8. **No real PHI goes to any model** in this build, and nothing ever goes to contributor models.
9. **The patient owns the record.** They can export it at any time, and deleting must really delete it (planned).
10. **Acting for someone else needs their yes.** A child under 18: the parent manages it, until 18. Another adult: nothing but their name until they say yes, and they choose view and/or act. Only the person, a parent of a minor, or an attested legal representative can sign. ✓
11. **Every crew workflow stops at a consent gate** and shows the full letter before anything is sent. A "no" escalates instead of stopping. Deadlines name their source; the person's own letter wins. ✓
12. **The support plan never gives medical advice,** and every suggestion cites the risk factor or benefit behind it. ✓
13. **The caller always says it's an AI calling with the patient's permission** and shares only name, date of birth, member ID and plan. ✓
14. **The swarm's existing invariants still hold:** immutable `SAFETY_BLOCK` / `SAFETY_SHA`, honest leverage only, and never tuning on the holdout split. See [CLAUDE.md](CLAUDE.md).

## 14. Repo layout

| Path | What it is |
|---|---|
| `src/patient/` | **The patient record**: `models.py` (data model), `buckets.py` (the four buckets and the panels), `store.py` (in-memory store and export), `demo.py` (demo patient) |
| `src/agents/guide.py` | PJ: next step, ask routing, safety rules |
| `src/agents/coverage.py` | Coverage agent |
| `src/agents/care_team.py` | Care Team agent (directory and verification call) |
| `src/agents/records.py` | Records agent (letter, signature, fax, clock, filing) |
| `src/agents/navigator.py` | Care Navigator (crisis check, need classification, pathways) |
| `src/agents/worker.py` | Swarm call worker (no booking tool) |
| `src/swarm/` | Swarm blackboard, events, 15-way dispatcher |
| `src/channels/fax.py` | The `FaxChannel` interface and `SimulatedFax` |
| `src/sim/payers.py` | Fictional insurers, benefits, employer EAPs, demo cards |
| `src/sim/providers.py` | Fictional directory: what it says vs. what's true |
| `src/sim/records_office.py` | What a fictional office sends back |
| `src/sim/` (other files) | Swarm personas, IVR trees, scenarios, the simulated office |
| `src/api/server.py` | FastAPI app: `/` is the patient dashboard, plus `/swarm` and the swarm API |
| `src/api/patient.py` | Patient API (`/api/p/*`) |
| `src/api/static/` | `home.html` (patient dashboard), `index.html` (swarm dashboard), `pj.webp` (PJ) |
| `src/llm.py`, `src/config.py`, `src/mock.py` | Meta Model API client, per-role models, offline mocks |
| `src/directory/`, `data/directory/` | Real provider data: NPPES and Plan-Net connectors (UHC, Cigna, Humana), plus the Phoenix cardiology snapshot ([docs/provider-data.md](docs/provider-data.md)) |
| `src/intake.py`, `src/voice.py` | Request parsing; speech to text with Muse Voice Transcribe |
| `.github/workflows/deploy.yml`, `scripts/deploy_lightsail.py` | Deploy to AWS Lightsail: automatically on merge, or by hand ([DEPLOY.md](DEPLOY.md), [docs/aws-hosting.md](docs/aws-hosting.md)) |
| `src/safety.py` | Swarm safety block and checks |
| `src/eval/` | Swarm judge and batch evals |
| `src/agents/circle.py`, `outreach.py`, `workflows.py`, `office_calls.py`, `actions.py` | Care circle, support plan, crew workflows, doctor's-office caller, action menu |
| `src/sim/counterparties.py`, `src/sim/pcp_office.py` | Fictional billing offices, plan appeal units, suppliers, state agency; a doctor's office phone menu with hold and transfers |
| `tests/` | `test_patient.py` (patient flow, navigator, safety), `test_family.py` (care circle, support plan, workflows, calls) and the swarm tests |
| `docs/` | `DEMO-PITCH.md` (3-minute script, kept current), `FAMILY-AND-AGING.md` (aging, families, market, frontier), `PLAN.md` (original swarm plan), `swarm-architecture.md`, `DATA-SOURCES.md`, `demo-script.md` (older swarm-only script) |

Planned additions:

- `src/channels/payer.py`, `directory.py` and `phone.py`: adapter interfaces modeled on `FaxChannel`.
- `src/agents/referrals.py` (referral requests already go through the Caller).
- `src/patient/db.py` (SQLite).
- `docs/COMPLIANCE.md`.

## 15. Build status and next steps

### Done (84 tests pass offline)

| Area | Status | Proof |
|---|---|---|
| Name-only start, session cookie, demo patient | ✅ | `test_name_only_start_no_password`, `test_demo_patient_fills_every_bucket` |
| Coverage: card → plain summary, benefits, EAP | ✅ simulated | `test_full_onboarding_flow` |
| PCP search, plus a verification call that corrects a stale fax and network status | ✅ simulated | `test_full_onboarding_flow` (2 corrections) |
| Records request: letter, signature check, fax, due date, response filed into buckets | ✅ simulated | `test_full_onboarding_flow`, `test_records_never_sent_unsigned`, `test_stale_fax_fails_until_verified` |
| Care Navigator: therapist on PPO with EAP, Medicaid, HMO specialist, physical therapy vs. talk therapy, crisis | ✅ rules | navigator tests, `test_crisis_always_first` |
| PJ won't answer medical questions | ✅ | `test_pj_never_answers_medical_questions` |
| Patient dashboard (mobile and desktop) | ✅ | Checked in a headless browser at iPhone and desktop widths |
| Scheduling Swarm at `/swarm` | ✅ simulated offices | Swarm tests |
| Live Meta Model API | ✅ swarm only | `scripts/smoke_meta.py` passed every check on Oct 27. A full 15-call swarm ran live on `muse-spark-1.3` (15/15 calls, 15/15 safety, about 25 s), and that run is the public replay (`recordings/demo.jsonl`). |
| Voice intake | ✅ swarm only | The 🎙 Speak button on `/swarm` records in the browser, and `src/voice.py` transcribes the recording with Muse Voice Transcribe (`POST /v1/asr/transcribe`). Verified on the live API. |
| Real provider directory | ✅ swarm only | `src/directory/` holds 677 Phoenix-area cardiologists from NPPES, plus the networks UHC, Cigna and Humana list for them in their public Plan-Net FHIR directories. This is step 1 of the swarm. See `docs/provider-data.md`. |
| Hosting | ✅ | Live on AWS Lightsail ([DEPLOY.md](DEPLOY.md)). Every merge to `main` redeploys automatically once the AWS secrets are added. |
| Action-menu home screen | ✅ | `test_home_leads_with_actions_and_the_demo_family`; checked in a headless browser at desktop and phone widths |
| Care circle: parent of a minor (ends at 18), consented helper, legal representative, pending consent | ✅ | `test_parent_manages_a_minor_and_access_ends_at_18`, `test_adult_sees_nothing_until_they_say_yes`, `test_a_helper_can_start_work_but_never_sign_for_an_adult` |
| Support plan from risk factors (older adult, child, teen), never advice | ✅ rules | `test_support_plan_*` |
| Crew workflows: bill dispute, prior-auth appeal → outside review, rides/aide/supplies, medical equipment, home care hours appeal, counselor request | ✅ simulated counterparties | `test_every_workflow_stops_for_consent_before_sending`, `test_a_denied_appeal_escalates_to_outside_review`, `test_bill_dispute_reports_the_money_saved` |
| Doctor's-office caller: phone menu, hold, transfer to the right person, reference number | ✅ simulated office | `test_office_call_works_the_menu_holds_and_gets_the_right_person` |
| Any Meta model call in the patient layer | ❌ | Everything in the patient layer is deterministic |

### Next, in priority order

Submission is due Nov 4, 9:00 PM ET. Aim to submit on Nov 3.

| # | Task | Acceptance criteria |
|---|---|---|
| 1 | **Point the Care Team agent at the real directory.** Use `src/directory/` for doctor search when the patient's insurer is UHC, Cigna or Humana, and keep the simulated directory for the demo cards. | Searching for a real Phoenix cardiologist shows the networks that insurer's directory lists, marked `unverified` until confirmed. |
| 2 | **Hook "Do it, PJ" (in-network) up to the swarm.** `POST /care/{id}/go?kind=in_network` starts a swarm run with the patient's plan and need. The task shows progress and the held slot. The patient confirms. | A held slot appears on the patient dashboard. Nothing is booked without the patient's yes. |
| 3 | **Give PJ its voice on Muse Spark** (`guide.ask` for chat answers), grounded on the record, with the safety block hashed like `SAFETY_SHA`. | Safety tests still pass with the live model. A 30-question red-team set (dosing, diagnosis, crisis) passes 100%. |
| 4 | **Read an insurance card photo into `Coverage`** with Muse Spark vision (fictional card images). | Upload a fake card photo, and the member ID and payer are read correctly. |
| 5 | **Build a simulated insurer portal and use computer-use on it.** The portal is a small fake page served by the app. | The Coverage agent logs into the fake portal with a fake demo login and reads benefits off the screen. |
| 6 | **Have Wonder plan the navigator's explanations.** Keep the rules for the facts; Wonder writes the plan and chases the steps. | Same ranked pathways as the rules, with plainer copy. |
| 7 | **Extract records:** a fictional PDF or fax image → `HealthItem`s via Spark vision. | A sample PDF fills Clinicals and Family & Genes with the correct flags. |
| 8 | **Build the Referrals agent** for `pcp_first`: draft the referral request to the PCP and track it. | The HMO dermatology flow ends with a referral task. |
| 9 | **Add a SQLite store** (`PATIENT_STORE_DIR` → a real database) and delete-my-data. | Data survives a restart, and delete removes everything. |
| 10 | **Reuse the swarm's voice intake for Ask PJ.** Call `src/voice.py` and reuse the browser WAV conversion from `index.html`. | The patient can speak the Ask PJ question. |
| 11 | **Record the demo video from `docs/DEMO-PITCH.md`** (keep that script current with every user-visible feature), with the swarm as the climax. | A 3-minute video is recorded. |
| 12 | **Write `docs/COMPLIANCE.md` and the pilot path.** | An honest posture, with no compliance claims. |

If behind schedule, cut in this order: 10, 9, 7, 5. Protect 2, 3 and 11.

### Demo story

See [docs/DEMO-PITCH.md](docs/DEMO-PITCH.md): the 3-minute script, Q&A answers, and a checklist tying each beat to the feature it shows. Update it with every user-visible change.

## 16. Open questions

- **Product name.** "PJ Health" is a placeholder. PJ is the GLTrax mascot, a Gila monster (they/them).
- **Hackathon Official Rules.** Which non-Meta tools are allowed (text-to-speech, fax), the submission format, and any healthcare-data rules. Still unverified.
- **Pilot vendors.** Which aggregator to use for payer Patient Access APIs, and which clearinghouse for 270/271.
- **Real calls.** Whether PJ should ever place real calls to offices during a pilot, and under what consent and disclosure script.
- **Caregiver access.** How family members and caregivers get access (proxy access) without sharing a login.
- **Check-in questions.** Where the Life & Connection and Routines questions come from (validated screeners or conversational check-ins), and how often PJ asks them.
