// Thin client for the CMS Blue Button 2.0 API (SMART on FHIR / OAuth2 + PKCE).
// Everything payer-specific lives here so other payers (via an aggregator
// like Flexpa) can be added as sibling modules with the same interface.

const BASE = process.env.BB_BASE_URL || "https://sandbox.bluebutton.cms.gov";

export const endpoints = {
  authorize: `${BASE}/v2/o/authorize/`,
  token: `${BASE}/v2/o/token/`,
  fhir: `${BASE}/v2/fhir`,
};

export function buildAuthorizeUrl({ state, challenge }) {
  const p = new URLSearchParams({
    client_id: process.env.BB_CLIENT_ID,
    redirect_uri: process.env.BB_REDIRECT_URI,
    response_type: "code",
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return `${endpoints.authorize}?${p}`;
}

export async function exchangeCode({ code, verifier }) {
  const res = await fetch(endpoints.token, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: process.env.BB_REDIRECT_URI,
      client_id: process.env.BB_CLIENT_ID,
      client_secret: process.env.BB_CLIENT_SECRET,
      code_verifier: verifier,
    }),
  });
  if (!res.ok) throw new Error(`Token exchange failed: ${res.status} ${await res.text()}`);
  return res.json(); // { access_token, refresh_token, expires_in, patient, ... }
}

export async function fhirGet(path, accessToken) {
  const res = await fetch(`${endpoints.fhir}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/fhir+json" },
  });
  if (!res.ok) throw new Error(`FHIR ${path} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// Follow Bundle.link[rel=next] pagination, capped for safety.
export async function fhirGetAll(path, accessToken, maxPages = 5) {
  let bundle = await fhirGet(path, accessToken);
  const entries = [...(bundle.entry || [])];
  for (let i = 1; i < maxPages; i++) {
    const next = (bundle.link || []).find((l) => l.relation === "next")?.url;
    if (!next) break;
    const res = await fetch(next, {
      headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/fhir+json" },
    });
    if (!res.ok) break;
    bundle = await res.json();
    entries.push(...(bundle.entry || []));
  }
  return entries.map((e) => e.resource);
}
