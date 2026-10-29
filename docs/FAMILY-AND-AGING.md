# Family care and the aging population

**Status (Oct 29, 2026):** built and tested offline: care circle, support plan, seven agent workflows, including a caller that phones the doctor's office, and the action-menu home screen. Everything runs on simulated insurers, offices and agencies. Since Oct 29 the crew runs live on Meta's models: Muse Spark calls the doctor's office and reads letters, bills and EOBs from photos; Muse Wonder maps the evidence to the plan's rules; Spark writes the letters and is PJ's chat. Rules are the guardrails and fallback.

## The idea in one paragraph

Healthcare is extremely complicated to navigate, and most of it falls on the person least equipped to do it: a 78-year-old on Medicare Advantage, or the adult daughter on hold for her. PJ puts the power back in the patient's hands. It finds every benefit and resource they already have, and PJ's crew of agents does the complicated work: the calls, the forms, the appeals and the follow-ups. The person (or the family member they chose) only decides and signs.

## Why this fits Y Combinator's "AI for the Aging Population"

YC's Fall 2026 Requests for Startups includes **AI for the Aging Population** (from YC partner Max Kolysh). Third-party summaries describe it as voice interfaces older adults can simply talk to, safety monitoring, help at home, and software that lets **family caregivers coordinate care**. The cited reasons: by 2030 about one in five Americans will be over 65, and about 53 million family members already provide unpaid care. One analysis points out that the buyer is often the adult child while the user is the parent, so the product has to serve both.

YC's own page couldn't be fetched from the build environment, so these points come from secondary sources; check the original before quoting it.

| YC request | How PJ answers it |
|---|---|
| AI for the Aging Population (Fall 2026) | Care circle for an older parent; a support plan built from age, plan and risk factors; agents that do the calls and appeals. |
| Multiplayer AI (Fall 2026) | One account, several people (parent, child, spouse), each with consent-based permissions. |
| AI-Native Compliance Infrastructure (Fall 2026) | Consent gates, signatures, every fact sourced, deadlines tracked, an audit trail on every workflow. |
| The $15-an-Hour Expert (Winter 2027, unverified) | PJ does a patient advocate's and benefits counselor's job for everyone. |
| Plaid for Government Benefits (Winter 2027, unverified) | Cost-help screening (Extra Help, Medicare Savings Programs, CHIP) and state caregiving-hours appeals. |

The Winter 2027 items come from a single unattributed article; treat them as provisional.

## What already exists (and the gap)

| Category | Examples | What they do | The gap PJ fills |
|---|---|---|---|
| Employer caregiving benefits | Wellthy, Cariloop, Homethrive | Human care coordinators and coaches, sold to employers and plans | Human-staffed and employer-gated; the consumer can't just open it. Little evidence of generative AI for consumers. |
| Family coordination apps | ianacare, CaringBridge, Lotsa Helping Hands | Rides, meals and shifts among family and friends | Coordinates people, not the healthcare system: no coverage, bills, appeals or records. |
| Navigation and advocacy | Transcarent (merged with Accolade, 2025) | Benefits Q&A, scheduling and triage; WayFinding 2.0 added agentic voice scheduling in Jan 2026 | Employer-sold, works inside one employer's plan design; no sign of agents filing appeals or disputing bills for the member. |
| Benefits screeners | NCOA BenefitsCheckUp (2,000+ programs, free) | Tells people what they may qualify for | Stops at "you may qualify"; the person still applies alone. PJ fills in the application for them to sign. |
| Medicare dementia programs | CMS GUIDE model (since July 2024) | Care coordination and respite for people with dementia and their caregivers | Only through participating practices; families don't know it exists. PJ surfaces it when memory concerns come up. |
| Portal proxy access | MyChart and other patient portals | A parent or caregiver sees one health system's portal | One system at a time, read-mostly. PJ spans plans, offices and agencies and does the work. |

Sources are listed at the end. Most are vendor or market summaries; confirm specifics before quoting them.

**Where PJ pushes the frontier:** the incumbents give people a human to call or a screen to read. PJ gives them a crew that acts: it calls 15 offices at once, reads a bill line by line against the EOB, assembles a prior-authorization appeal from the records and a doctor's letter, files a fair-hearing request before the deadline that keeps home care hours in place, and escalates when the answer is no. It works for the person, across every plan and agency, and it never acts without their yes.

## What's built

### 1. Care circle: manage care for an older parent or a child

`src/agents/circle.py`. One account holds up to 8 people. Access follows real life and the law, and the person can always see it:

| Situation | Authority | What the account holder can do |
|---|---|---|
| A child under 18 | `parent_of_minor` | View, act and approve (sign). Ends automatically at 18; the adult child then decides. |
| Another adult who said yes | `consented_helper` | What the person chose: view, or view and have PJ act. They still sign and approve themselves. |
| Healthcare power of attorney or guardian | `legal_representative` | View, act and approve, signing as "personal representative of …". Attested, not verified, in this demo. |
| An adult who hasn't said yes | `pending_consent` | Nothing but their name. The only action is "Ask them to say yes". |

Teens: the support plan notes that some of a teen's visits can be private, and PJ respects that.

### 2. Support plan from risk factors

`src/agents/outreach.py`. PJ combines what's on the record (age, coverage, employer EAP) with what the person or caregiver tells it (lives alone, fell in the past year, takes 5 or more medicines, memory changes, hard to afford, no ride, caregiver stretched thin…). It proposes covered next steps, each with the reason, the source and the cost:

- Yearly Medicare Wellness Visit; well-child checkups and vaccines.
- Fall-risk check and covered strength and balance therapy.
- A free medication review (Medication Therapy Management).
- Memory check at the Wellness Visit; Medicare's GUIDE program if a doctor diagnoses dementia.
- Specialist follow-ups that really take the plan (the swarm).
- Daily check-in calls for people who live alone.
- Free rides when the plan covers them; community rides when it doesn't.
- Cost help: Extra Help and Medicare Savings Programs, Medicaid or CHIP for kids.
- Caregiver support through the employer's EAP or the Area Agency on Aging.
- Unused benefits: free dental cleanings, $0 video visits.

It never diagnoses or advises; a test scans every suggestion for diagnostic or dosing language. The person taps "Do it, PJ" or "Not now".

### 3. Agent workflows: PJ's crew does the hard jobs

`src/agents/workflows.py`, counterparties in `src/sim/counterparties.py`. Same pattern as the scheduling swarm, applied to everything else:

| Workflow | The crew | What happens |
|---|---|---|
| **Call the doctor's office for anything** | Caller agent, Tracker | Referrals, refills, letters, orders, nurse questions, records, appointments, billing: works the phone menu, waits on hold, gets transferred to whoever really handles it, says it's an AI calling with permission, shares only name, birthday, member ID and plan, and brings back a reference number and the full transcript. Other workflows use the same caller for the doctor's letter or order. |
| **Contest a medical bill** | Billing, Claims, Writer agents, Tracker | Gets the itemized bill, matches every line to the plan's EOB (duplicates, out-of-network pricing for an in-network office, a free checkup billed, payment not credited), drafts the dispute, asks to hold collections, reports the money saved. |
| **Appeal a prior-authorization denial** (multi-agent) | Policy, Records, Caller, Writer, Submitter agents, Tracker | Reads the denial and the filing window, pulls evidence from the records only, gets the doctor's letter of medical necessity, maps evidence to the plan's criteria, files (urgent when it qualifies), and on a "no" prepares an independent outside review. |
| **Request rides, an aide or supplies** | Coverage, Caller, Writer, Submitter agents, Tracker | Checks the benefit, gets the doctor's order when required (not for rides), submits, books. |
| **Renew or appeal medical equipment** | Coverage, Caller, Care team, Writer, Submitter agents, Tracker | Oxygen, CPAP supplies, wheelchair, hospital bed: renews before the approval lapses, or appeals a denial with updated notes and an in-network supplier. |
| **Appeal a cut to home care hours** | Policy, Records, Caller, Writer, Submitter agents, Tracker | Reads the state notice, files for a fair hearing in time to keep the current hours during the appeal, with the doctor's statement of care needs. |
| **Find a counselor who can really see you** | Coverage agent, Scheduling swarm, Writer, Submitter agents, Tracker | Checks the plan and EAP, calls in-network counselors at once, and when none can see you soon, asks the plan for a network exception (single case agreement). |

Rules every workflow follows (enforced by tests):
1. Agents do every step they can on their own.
2. **Consent gate:** the full letter is shown, and nothing is sent until someone allowed to sign does. A helper can start a workflow but can't sign for an adult.
3. Deadlines name their source and say "the letter wins". The typical windows used (65 days for Medicare Advantage appeals, 60 for Medicaid, 180 otherwise; about 10 days to keep home care hours during an appeal) are approximations, marked as such.
4. A "no" queues the next level instead of ending.
5. Agents never invent clinical facts: evidence comes from the records, what the person told PJ, or the doctor's office.

### 4. The home screen is a menu of actions

`src/agents/actions.py` and `src/api/static/home.html`. The page leads with "What should PJ do?":
- Personal actions: find a doctor who really takes the plan, benefits not used yet, coverage, records, checkup or Wellness Visit, tell PJ about yourself, manage care for a parent or child.
- PJ's crew jobs, grouped as "Get care" (led by the scheduling swarm), "Fight a wrong bill or a no", and "Get what the plan owes you".

Workflows in progress, the support plan, the Ask PJ chat, the four buckets, coverage, care team and records all remain, lower on the page.

## Demo family (fictional)

`src/patient/demo.py`:
- **Alex Rivera** (account holder): employer PPO with an EAP; stretched thin as a caregiver.
- **Rosa Rivera** (Alex's mother, 78): Bluewater Medicare Advantage HMO. Lives alone, fell in April, takes 6 medicines, heart condition, stopped driving, hard to afford. Alex holds healthcare power of attorney (attested). PJ already won a bill dispute ($433 saved), and an appeal for home physical therapy is waiting for Alex's signature.
- **Leo Rivera** (Alex's son, 9): Medicaid; mild asthma; flu shot due.

## Next steps (in order)

1. Wire the scheduling swarm to "Do it, PJ" from the support plan and the counselor workflow (CLAUDE.md next step 2).
2. ✅ Done Oct 29: Spark vision reads bills, EOBs and denial letters; Wonder maps evidence; Spark drafts letters with code checks.
3. An adversarial plan reviewer (Muse Spark Open on Baseten) that tries to deny each appeal before it's sent, and a call gym of hundreds of simulated receptionists (Fireworks).
4. Voice-first Ask PJ for older users (`src/voice.py`), plus a large-text mode.
5. Real-world path: identity verification, document checks for power of attorney, HIPAA authorization forms, e-signature, a fax API under a BAA, and state-by-state appeal rules. See `docs/COMPLIANCE.md` (to be written).

## Sources

- [Medium: YC's 2026 RFS wishlist](https://medium.com/@tanishshenoy/yc-has-dropped-its-2026-request-for-startup-wishlist-4313275d32fb)
- [Mining Wells: all 13 Fall 2026 ideas explained](https://miningwells.com/blog/yc-request-for-startups)
- [WorthvieW: YC Fall 2026 RFS explained](https://www.worthview.com/y-combinators-fall-2026-request-for-startups-all-13-ideas-explained/)
- [BigIdeasDB: YC RFS 2026](https://bigideasdb.com/yc-request-for-startups-2026)
- [Whatfinger: Plaid for Government Benefits](https://startup.whatfinger.com/2026/10/28/plaid-for-government-benefits/)
- [Caring Village: caregiver apps 2026](https://caringvillage.com/blog/caregiver-tech/caregiver-apps-for-families/)
- [Neela: AI caregiving apps 2026](https://www.neelacares.com/library/top-ai-caregiving-apps-for-busy-us-families-in-2026)
- [Shortlister: elder care vendors 2026](https://www.myshortlister.com/elder-care-service-providers/vendor-list)
- [Fact.MR: digital caregiver platforms market](https://www.factmr.com/report/digital-caregiver-platforms-market)
- [Fierce Healthcare: Transcarent agentic AI](https://www.fiercehealthcare.com/ai-and-machine-learning/transcarent-builds-out-agentic-ai-features-benefits-navigation-clinical)
- [Healthcare Dive: Transcarent to acquire Accolade](https://www.healthcaredive.com/news/transcarent-acquire-accolade-621-million-health-benefits-navigation/736798/)
- [Transcarent WayFinding](https://transcarent.com/wayfinding)
- [NCOA: Boost Your Budget Week, BenefitsCheckUp](https://www.ncoa.org/article/ncoa-promotes-boost-your-budget-week-to-help-9-million-eligible-older-adults-access-life-saving-benefits/)
- [LeadingAge: GUIDE model](https://leadingage.org/serialpost/guide-model-aid-for-people-living-with-dementia-unpaid-caregivers/)
- [CMS GUIDE payment methodology](https://www.cms.gov/priorities/innovation/files/guide-payment-methodology-paper.pdf)
