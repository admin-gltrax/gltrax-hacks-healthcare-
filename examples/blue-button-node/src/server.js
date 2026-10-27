import "dotenv/config";
import express from "express";
import session from "express-session";
import { makePkce, makeState } from "./pkce.js";
import { buildAuthorizeUrl, exchangeCode, fhirGet, fhirGetAll } from "./bluebutton.js";
import { normalizeCoverage, normalizeEob, ytdSummary } from "./normalize.js";

const app = express();

app.use(
  session({
    secret: process.env.SESSION_SECRET || "dev-only",
    resave: false,
    saveUninitialized: false,
    // MemoryStore is for local dev only. Use Redis/DB-backed sessions in prod
    // and encrypt tokens at rest.
    cookie: { httpOnly: true, sameSite: "lax" },
  })
);

const requireAuth = (req, res, next) =>
  req.session.tokens ? next() : res.status(401).json({ error: "Not connected. Visit /login" });

app.get("/", (req, res) => {
  res.send(
    req.session.tokens
      ? `<p>Connected. Try <a href="/api/benefits">/api/benefits</a>, <a href="/api/coverage">/api/coverage</a>, <a href="/api/eob">/api/eob</a>.</p>`
      : `<p><a href="/login">Connect Medicare (sandbox)</a></p>`
  );
});

// 1) Start OAuth: PKCE + state
app.get("/login", (req, res) => {
  const { verifier, challenge } = makePkce();
  const state = makeState();
  req.session.pkce = { verifier, state };
  res.redirect(buildAuthorizeUrl({ state, challenge }));
});

// 2) Callback: verify state, swap code for tokens
app.get("/callback", async (req, res) => {
  try {
    const { code, state, error } = req.query;
    if (error) return res.status(400).send(`Authorization error: ${error}`);
    const saved = req.session.pkce;
    if (!saved || state !== saved.state) return res.status(400).send("State mismatch");

    req.session.tokens = await exchangeCode({ code, verifier: saved.verifier });
    delete req.session.pkce;
    res.redirect("/");
  } catch (e) {
    res.status(500).send(e.message);
  }
});

// 3) Data endpoints
app.get("/api/patient", requireAuth, async (req, res) => {
  try {
    res.json(await fhirGet("/Patient/", req.session.tokens.access_token));
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/api/coverage", requireAuth, async (req, res) => {
  try {
    const raw = await fhirGetAll("/Coverage/", req.session.tokens.access_token);
    res.json(normalizeCoverage(raw));
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/api/eob", requireAuth, async (req, res) => {
  try {
    const raw = await fhirGetAll("/ExplanationOfBenefit/", req.session.tokens.access_token);
    res.json(normalizeEob(raw));
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/api/benefits", requireAuth, async (req, res) => {
  try {
    const token = req.session.tokens.access_token;
    const [cov, eobRaw] = await Promise.all([
      fhirGetAll("/Coverage/", token),
      fhirGetAll("/ExplanationOfBenefit/", token),
    ]);
    const eobs = normalizeEob(eobRaw);
    res.json({
      coverage: normalizeCoverage(cov),
      ytd: ytdSummary(eobs),
      note: "Spend rollup only. Deductible/OOP accumulators are not available via Patient Access APIs.",
    });
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.post("/logout", (req, res) => req.session.destroy(() => res.redirect("/")));

app.listen(process.env.PORT || 3000, () =>
  console.log(`http://localhost:${process.env.PORT || 3000}`)
);
