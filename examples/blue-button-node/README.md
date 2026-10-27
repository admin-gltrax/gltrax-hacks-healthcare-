# Payer FHIR Starter (Blue Button 2.0 sandbox)

Minimal Node server that runs the full member-authorized flow: OAuth 2.0 +
PKCE, FHIR R4 reads, and normalization into your own shape.

## Setup
1. Register an app at https://sandbox.bluebutton.cms.gov
   - Callback URL: `http://localhost:3000/callback`
   - Grant type: authorization code; client type: confidential
   - Scopes: Patient, Coverage, ExplanationOfBenefit (plus profile)
2. `cp .env.example .env` and fill in client ID / secret
3. `npm install && npm start`
4. Open http://localhost:3000, click Connect, log in with a sandbox
   beneficiary (credentials are shown in the sandbox developer docs/portal).

## Verify each step
- `/login` redirects to `sandbox.bluebutton.cms.gov` login. If not, check `BB_CLIENT_ID`.
- After login you land back on `/` showing "Connected". If you get "State mismatch", cookies are blocked or the session was lost.
- `/api/coverage` returns a non-empty array. If 401 from FHIR, the scopes on your registered app are missing.
- `/api/eob` returns claims; `/api/benefits` returns the YTD rollup.

## Layout
- `src/bluebutton.js`: payer-specific OAuth + FHIR client (swap/add payers here)
- `src/normalize.js`: FHIR to your app's own data shape
- `src/pkce.js`: PKCE verifier/challenge and state
- `src/server.js`: routes and session handling

## Next steps
1. Add refresh-token handling (store tokens server-side, encrypted).
2. Add a second provider module (Flexpa test mode) behind the same interface.
3. Replace MemoryStore with a real session/token store.
4. Build the benefits layer: join the EOB rollup with public plan data
   (SBC, CMS plan files) for deductible and OOP max.
5. Mobile client: use the system browser (ASWebAuthenticationSession / Custom Tabs)
   to hit `/login`, and keep tokens on the server.

## Caveats
- Endpoint paths and scopes are from memory; confirm against the current Blue Button docs.
- Blue Button covers Medicare only. Commercial plans need an aggregator or per-payer portals.
- Not production-ready: no token encryption, CSRF protection on `/logout`, rate limiting, or audit logging.
- Consumer apps are outside HIPAA but subject to the FTC Health Breach Notification Rule and California CMIA/CCPA.
