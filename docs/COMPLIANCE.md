# Compliance posture (honest version)

> **Status (Oct 29, 2026):** PJ Health is a hackathon build that runs on **fictional data only**. It makes **no compliance claims**: it is not HIPAA-compliant, not certified, and not ready for real patients. This page says what the code already enforces, what the law would require before real use, and what we don't know yet. It is not legal advice; a healthcare attorney reviews it before any pilot.

## 1. What the code enforces today

Each line is enforced in code and covered by a test (`tests/`), not just written in a prompt.

| Guarantee | Where | Test |
|---|---|---|
| Fictional data only: 555-01xx numbers, `SIM-` IDs, every sample document stamped "fictional" | `src/sim/`, `src/sim/documents.py` | `test_family.py` (fictional numbers) |
| Nothing is sent without a signature from someone allowed to sign | `workflows.approve`, `records.send` | `test_a_helper_can_start_work_but_never_sign_for_an_adult` |
| An adult sees nothing until they consent by typing their own name; a parent's authority ends at 18 | `src/agents/circle.py` | `test_adult_sees_nothing_until_they_say_yes`, `test_parent_manages_a_minor_and_access_ends_at_18` |
| Callers say they're an AI to every person they reach, share only name, date of birth, member ID and plan, and never claim to be human | `src/safety.py` (`SAFETY_BLOCK`, hash-pinned), `src/agents/office_caller.py` | `test_caller_uses_the_same_immutable_safety_block…`, `test_caller_that_skips_the_ai_disclosure_fails_the_check` |
| A reference number counts only if the office really said it | `office_caller._summary` | `test_a_reference_number_the_office_never_said_is_not_trusted` |
| Crisis words get 988 / 911 before any model sees them; medical questions go to the doctor or nurse line, never to a model | `guide.ask_live`, `navigator.CRISIS` | `test_crisis_and_medical_questions_never_reach_the_model`, `test_pj_red_team` (20 cases, 100%) |
| PJ's chat can only *propose* work; a person taps to start it | `guide._run_tool` | `test_pj_red_team` |
| Letters cite only facts on file: every number must come from the facts, no dosing, member ID present; a failing draft never reaches the signature | `appeals.check_letter` | `test_a_letter_that_invents_a_number_never_reaches_the_signature` |
| Evidence citations must point at real records; a rule is "met" only with evidence | `appeals.clean_map` | `test_appeal_from_a_photo_of_the_denial_letter` |
| Money math is done in code, not by a model | `reader.match_bill` | `test_the_money_math_is_code_not_the_model` |
| Uploaded document images are read, then discarded; only extracted fields are kept | `workflows._document`, `Workflow.documents` | `test_appeal_from_a_photo…` (`"base64" not in` the stored record) |
| No `-contributor` models (Meta trains on those) | `ai.model_for` | `test_budget_caps_and_contributor_models_are_refused` |
| Model spend is capped per server and per account per day | `ai.Budget` | same |
| Session tokens are stored only as SHA-256 hashes; sessions expire after 7 days; "Delete my data" removes everything and can't be undone by a late background job | `src/patient/store.py` | `test_sqlite_store_survives_a_restart_and_delete_means_delete` |
| The patient-facing crew (caller, reader, strategist, writer, PJ's chat) can only run on Meta's Model API; partner credits run simulators, the adversary and judges | `ai.model_for` | `test_patient_facing_crew_stays_on_meta_and_partner_roles_use_their_own_keys` |
| Caller safety holds at scale: 600 simulated hostile offices (data fishers, fake "HIPAA verification", AI refusers, voicemail, Spanish-first), every call scored in code | `src/sim/gym.py`, `scripts/call_gym.py` | `test_the_gym_catches_*`; latest run in `docs/evals.md` |
| The adversarial reviewer can only cite the plan's real rules and never writes letter text; revisions must pass the letter checks | `src/agents/reviewer.py` | `test_objections_must_cite_real_rules_and_the_reviewer_never_writes_the_letter`, `test_a_revision_that_fails_the_letter_checks_is_never_used` |
| No passwords, ever: not for PJ, not for insurer portals | sign-in is name-only (demo); PJ's chat refuses logins | `test_pj_red_team` |

## 2. Which laws would apply to a real launch

### Health privacy
- **HIPAA.** A consumer app that the patient chooses, and that acts at the patient's direction, is usually **not** a HIPAA covered entity or business associate. That changes the moment PJ works *for* a health plan, employer plan or provider (for example, sold to a Medicare Advantage plan): then PJ is a **business associate** and needs BAAs, the Security Rule (risk analysis, access controls, audit logs, encryption) and breach notification.
- **FTC Health Breach Notification Rule** (updated 2024). Health apps outside HIPAA that hold identifiable health information must notify users, the FTC and sometimes the media after a breach, and "breach" includes sharing without authorization. The FTC Act (Section 5) also covers privacy promises we make.
- **State laws.** Washington's My Health My Data Act (consent before collecting consumer health data, a private right of action), California's CMIA and CCPA/CPRA, and similar laws in other states. Plan for the strictest one.

### Acting for someone else
- **Personal representatives** (HIPAA, 45 CFR 164.502(g)): a healthcare power of attorney or guardian can act for an adult; parents usually act for minors, **except** where state law lets the minor consent to their own care (often reproductive, mental health, substance use). The care circle's teen-privacy note is a start, not an implementation.
- **Appeals need the right paperwork.** For a Medicare Advantage appeal filed by someone else, the plan typically needs an **Appointment of Representative** (form CMS-1696) or equivalent legal documentation. The demo's "attested" power of attorney must become a verified document upload.
- **Right of access** (45 CFR 164.524): the records request PJ drafts is the patient's right; real use needs identity verification and the office's preferred form.

### Calls, faxes and AI
- **Automated calls.** The FCC ruled in 2024 that AI-generated voices are "artificial" voices under the TCPA. Calls to consumers' phones need prior consent; calls to a business line such as a doctor's office are treated differently, but some offices route to cell phones. Real calls need a counsel-reviewed TCPA posture.
- **Call recording.** Transcribing a call is recording it. About a dozen states (including California) require every party's consent, so the caller must announce it at the start.
- **AI disclosure.** PJ already discloses on every call. Several states have or are passing bot-disclosure rules; disclosing by default covers them.
- **Fax.** Real records and appeals need a fax provider that signs a BAA.

### Insurance appeals and bills (what the deadlines rely on)
- **Medicare Advantage:** 65 days from the notice to request reconsideration (42 CFR 422 subpart M); expedited decisions in 72 hours.
- **Medicaid:** managed-care appeals are typically 60 days. To **keep services during an appeal**, the request usually has to be filed within about 10 days of the notice (42 CFR 431.230–231, 438.420).
- **Employer and Marketplace plans:** at least 180 days for internal appeals, then independent external review.
- **Billing:** the No Surprises Act and in-network contracts limit balance billing; the EOB's "you owe" is the ceiling for covered in-network care.

PJ treats all of these as **typical** windows and says so. When the reader agent reads the actual letter, **the letter's date wins** (`Workflow.deadline_note`).

## 3. Models and vendors

| Vendor | Used for | Real-PHI status |
|---|---|---|
| Meta Model API (Muse Spark, Muse Wonder) | Caller, receptionist simulator, reader, strategist, writer, PJ's chat | **Unknown whether Meta signs a BAA.** Until one is in place, no real PHI goes to it. |
| Fireworks / Baseten (Muse Spark Open, open weights) | Built: call gym receptionists, the insurer-side appeal reviewer, the second judge. Never patient-facing (enforced in `ai.model_for`). Fictional data only. | Check each vendor's BAA and data-retention terms before any real data. A self-hosted open-weights deployment is the likely path for PHI. |
| Open text-to-speech (Kokoro-82M, open weights; Baseten deployment planned) | The simulated voice call and the speech-to-text eval only. **Off by default** (`VOICE_TTS=off`): whether the hackathon allows non-Meta TTS is unconfirmed. | Synthetic voices, fictional people; no real audio is ever recorded. |
| AWS Lightsail | Hosting the demo | AWS offers a BAA for HIPAA-eligible services. Check that Lightsail containers are covered, or move to ECS or Fargate. |

The `-contributor` model variants are never used: Meta trains on those prompts.

## 4. Before a pilot with real people (in order)

1. **Real authentication:** passkeys or email plus a one-time code, and identity proofing (IAL2) before records or appeals.
2. **Verified authority:** upload and verify the power of attorney or guardianship and CMS-1696, and store the documents.
3. **Data layer:** encryption at rest (managed Postgres with KMS), field-level encryption for identifiers, a 90-day append-only audit log, a retention policy, and tested deletion.
4. **Vendor BAAs:** model provider (or self-hosted Muse Spark Open), fax, hosting, email.
5. **Calls:** a counsel-reviewed TCPA posture, a recording-consent announcement, opt-out handling, and a human escalation line.
6. **Safety evals in CI on every prompt change:** the PJ red team at 100%, caller safety at 100% over a large simulated call set (the call gym exists: `scripts/call_gym.py`), and reader accuracy above an agreed threshold on a labeled set (`scripts/eval_reader.py`, 33 documents x 4 photo qualities).
7. **A human-in-the-loop review** of appeals before sending, until the outcome data supports trusting the crew.
8. **Policies:** privacy notice, terms, incident response, and an FTC breach-notification runbook.

## 5. What we don't know yet

- Meta's Official Rules for the hackathon on healthcare data and phone calls.
- Whether Meta signs BAAs for the Model API.
- The exact TCPA treatment of AI calls to provider offices that forward to mobile phones.
- State-by-state rules on a parent's access to a teen's records, which PJ must follow per state.
