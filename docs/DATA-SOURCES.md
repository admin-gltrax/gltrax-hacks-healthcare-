# Data sources, sandboxes and fake servers

Research from the planning phase, written down so future sessions do not redo it. **Not part of the hackathon build**: the swarm runs on fully simulated offices. This is the map for (a) making the simulation realistic and (b) the post-hackathon path to real data.

Status tags: **[verified Oct 27 2026]** = checked against a source this session; **[from memory]** = unverified, check before relying on it.

## 1. Eligibility (X12 270/271)

- 271 is not a public feed; it is a per-member transaction through a clearinghouse. [from memory]
- Clearinghouses/aggregators named in the planning chat: Availity, Optum (ex-Change Healthcare), Waystar; developer-friendly: Stedi, Pverify. Stedi advertises a free Basic plan and sandbox accounts (pricing page and sandbox doc exist) but what the sandbox returns was **not** confirmed. [existence verified, details unverified]
- Why it matters here: real eligibility would replace the simulated "does this office take my plan" answer. The swarm exists because eligibility and directories are unreliable.

## 2. Member-authorized FHIR (Patient Access APIs)

- Rule summary (the 2020 CMS Interoperability and Patient Access final rule) [verified Oct 27 2026 against an HFMA summary]:
  - Patient Access API: Medicare Advantage orgs, Medicaid/CHIP (FFS and managed care), QHP issuers on the federal exchanges.
  - Provider Directory API: MA orgs and Medicaid/CHIP; **QHPs on the federal exchanges are exempt**.
  - Formulary data: MA-PD plans via the Patient Access API; Medicaid/CHIP covered-drug and preferred-drug lists.
  - Standards: FHIR R4 (4.0.1), OpenID Connect, SMART App Launch 1.0.0, USCDI.
  - **Correction to earlier chat claims:** CARIN Blue Button and Da Vinci PDex / Plan-Net are *implementation guides plans commonly follow*, not standards the rule itself mandates. [verified]
- Later rules (prior-authorization / CMS-0057-F, 2024) add more APIs and dates. [from memory, verify before citing]
- Consumer-app aggregators named earlier: Flexpa, Metriport, 1up Health, Health Gorilla, Particle, Fasten. [from memory]
- Consumer apps are usually outside HIPAA but subject to the FTC Health Breach Notification Rule and state laws (e.g. California CMIA/CCPA); vendors that touch PHI for a covered entity need BAAs. [from memory; not legal advice]

## 3. Sandboxes and fake servers

| Source | What you get | Status |
|---|---|---|
| **CMS Blue Button 2.0 sandbox** (sandbox.bluebutton.cms.gov) | Medicare claims (Patient, Coverage, ExplanationOfBenefit) for synthetic beneficiaries; register an app, OAuth2 + PKCE | Exists per the CMS site; exact registration steps and scopes were not re-read. The docs moved to bluebutton.cms.gov/api-documentation. [partly verified] |
| **Flexpa test mode** | Test API keys; synthetic insurers **FooMedical** (test logins on the docs page) and **Acme Health Plan** (pick a patient, no credentials); portal scenarios; Epic/Cerner/Athena sandboxes; TEFCA test identities. Shows response *shape*, not real-world noise or latency | [verified Oct 27 2026] |
| **HAPI public FHIR server** (hapi.fhir.org) | Open test server, anyone can post resources. Never put real data in it | [from memory] |
| **SMART Health IT launcher** | Test SMART-on-FHIR launches and sandboxes | [from memory] |
| **Epic on FHIR** (open.epic.com) | Public sandbox with test patients | [from memory] |
| **Synthea** | Open-source synthetic patient generator (histories, claims, EOBs). Best source for realistic fake patients and a local FHIR server | [from memory] |
| **Inferno, CARIN / Da Vinci reference implementations** | Conformance testing and reference servers for the IGs | [from memory] |

Recommended use here: generate patients with Synthea, stand up HAPI locally, and use that to test an intake-from-claims path. Only the simulated offices matter for the hackathon score.

## 4. Public data (no authorization needed)

- **NPPES / NPI Registry API**: provider names, specialties, practice addresses. The realistic seed for office lists. [from memory]
- **CMS data**: Medicare Advantage landscape files, Marketplace/QHP public-use files, Marketplace API (needs a key). [from memory]
- **Payer provider directories**: public web or Plan-Net FHIR for MA/Medicaid plans (see section 2 for who must publish). These are exactly the data the "directory vs reality" counter says is wrong. [from memory]
- **Formularies**: payer-published files; MA-PD formularies via the Patient Access API. [from memory]
- **Price transparency machine-readable files** (payers) and **SBCs** (Summary of Benefits and Coverage): deductible / out-of-pocket maximums for a benefits layer. [from memory]

## 5. How this connects to the build

- `src/sim/` fabricates offices; a future `directory/` module (designed in `docs/swarm-architecture.md`, **not built**) would pull NPPES + Plan-Net into a `Provider` shape to seed `OfficeScenario` and to power the truth counter with real directory claims.
- `examples/blue-button-node/` is the earlier Node starter for the member-authorized flow (OAuth2 + PKCE, Coverage, EOB, normalize). Never run against anything but the sandbox; paths and scopes were from memory.
- Real-world calling (telephony, consent, AI-voice disclosure rules) is out of scope until a pilot; see `docs/PLAN.md`. Recording-consent and AI-voice rules are state/FCC matters: verify before any real call.
