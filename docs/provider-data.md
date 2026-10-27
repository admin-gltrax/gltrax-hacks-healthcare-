# Live provider network data

> **Status.** The NPPES connector is built (`src/directory/nppes.py`); `data/directory/phoenix-cardiology.json` holds 677 Phoenix-metro cardiologists (fetched 2026-10-27). No payer connector yet. The swarm still calls the fixed, fictional 15-office demo. Real directory data is meant for the "directory says" side; simulated receptionists must never act under real practice names.

## Scope

Start with one metro, one specialty (cardiology) and a few Medicare Advantage plans that publish FHIR provider directories, then add payers one connector at a time. Every state and plan is a data-engineering project (hundreds of payers, multi-TB Transparency in Coverage files) and is out of scope.

## Sources checked (2026-10-27)

### NPPES NPI Registry: works, no key

`GET https://npiregistry.cms.hhs.gov/api/?version=2.1&taxonomy_description=Cardiovascular%20Disease&city=Phoenix&state=AZ&enumeration_type=NPI-1&limit=200`

- Identity, credential, taxonomy (specialty), practice address and phone for every provider. No network or plan data.
- Use the NPI as the join key across all sources.
- `taxonomy_description=cardiology` returns nothing; use the NUCC description (`Cardiovascular Disease`, `Interventional Cardiology`, `Clinical Cardiac Electrophysiology`).

### Aetna Provider Directory API (DaVinci PDex Plan-Net, FHIR R4): needs registration

From the developer portal's API library (`developerportal.aetna.com/apis`) and its Swagger specs (`https://developerportal.aetna.com/managedcontent/yaml/<SwagerFile>.yaml`).

- **Base URL (production):** `https://apif1.aetna.com/fhir/v1/providerdirectorydata` for Commercial and Medicare (Plan-Net IG 1.2.0); `.../v1/providerdirectory` for Medicaid (IG 1.1.0). The sandbox host `vteapif1.aetna.com/fhirdemo` only serves Patient Access, not the directory.
- **Auth:** OAuth2 client credentials. Register on the portal, create a Third-Party application with environment "Production", subscribe to products `public-providerdirectory-fhir` and `public-medicare-providerdirectory-fhir`. Token URL `https://apif1.aetna.com/fhir/v1/fhirserver_auth/oauth2/token`, scope `Public NonPII`. Client ID and secret go in environment secrets, never in the repo.
- **Search parameters (from the specs):**

| Resource | Query parameters |
|---|---|
| `Location` | `address-city`, `address-state`, `address-postalcode:exact`, `address`, `organization`, `partof`, `type`, `_include`, `_revinclude`, `_count`, `_page_token`, `_lastUpdated` |
| `PractitionerRole` | `specialty`, `location`, `practitioner`, `organization`, `network`, `role`, `identifier`, `_include`, `_count`, `_page_token`, `_lastUpdated` |
| `Practitioner` | `name`, `family`, `given`, `_id`, `_revinclude`, `_count`, `_page_token` (no NPI search; get NPIs via `PractitionerRole`) |
| `Organization` | `name`, `address`, `type`, `partof`, `_profile`, `_include`, `_revinclude` |
| `InsurancePlan` | `coverage-area`, `network`, `owned-by`, `type`, `name`, `identifier`, `period` |
| `HealthcareService`, `OrganizationAffiliation` | (see specs) |
| `$export` / `$exportstatus/{id}` | bulk export, `_type`, `_since`, `Prefer: respond-async` |

Paging is by `_page_token`, not `_offset`.

## NPPES connector

```bash
python -m src.directory.nppes --metro phoenix --specialty cardiology   # ~1 minute, no key
```

- Queries each cardiology taxonomy statewide (Cardiovascular Disease, Interventional Cardiology, Clinical Cardiac Electrophysiology, Advanced Heart Failure and Transplant Cardiology), pages 200 at a time, and splits by ZIP3 if a query hits the API's 1200-row cap.
- Keeps active individual providers with at least one practice location in the metro. Metro = Maricopa + Pinal counties, approximated as ZIP3 850-853 minus the Yuma, La Paz, Pima, Yavapai, Mohave and Gila ZIPs under those prefixes. A few Pinal towns under 856/857 are not covered.
- Writes `Provider` records (`src/schemas.py`) with every in-metro practice location; `network` stays empty until a payer source fills it.

## Planned payer join (one metro)

1. NPPES: all cardiology NPIs in the metro → `Provider` rows (schema in `docs/swarm-architecture.md`).
2. Aetna: `Location?address-city=…&address-state=…` → `PractitionerRole?location=…&specialty=<NUCC code>&_include=PractitionerRole:practitioner` → network references; `InsurancePlan?coverage-area=…` → plan ↔ network.
3. Join on NPI; write `network[{plan_id, status, confidence, last_verified, source:"directory"}]`.
4. Refresh nightly with `_lastUpdated`; consider `$export` once the per-metro flow works.

## Blockers

- Aetna app registration and client credentials (owner's action on the portal).
- The cloud environment's network policy blocks `apif1.aetna.com`; add it under Allowed domains. `npiregistry.cms.hhs.gov`, `developerportal.aetna.com` and `vteapif1.aetna.com` are already reachable.
