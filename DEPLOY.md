# Hosting guide

The app is one container running one process. Anyone with the URL can watch a **recorded replay** (free, no credentials). **Live runs** spend Meta Model API credits, so they require an access token.

## Deploy on Render (about 10 minutes)

1. Sign in at render.com and connect your GitHub account.
2. **New > Blueprint**, choose this repository. Render reads `render.yaml`.
3. When prompted, paste your `MODEL_API_KEY` (Meta Model API key). It is stored by Render and never committed.
4. Apply. The first build takes a few minutes. The health check is `/healthz`.
5. Open the service URL. Click **Replay recorded run** to confirm it works.
6. For live runs, copy `APP_ACCESS_TOKEN` from the service's **Environment** tab (Render generated it), paste it into the token box on the dashboard, and click **Start live swarm**. Share the token with Scott only.

`plan: starter` is a paid instance: free instances sleep when idle, so the first visitor (or a judge) would wait through a cold start. Check Render's current pricing before applying.

## Replace the placeholder recording with a real one

`recordings/demo.jsonl` currently comes from the **scripted mock models**, and the replay banner says so. Once the worker prompt is calibrated on the real models:

```bash
python scripts/make_recording.py        # real models; writes recordings/demo.jsonl
# review it on the dashboard, then
git add recordings/demo.jsonl && git commit -m "Record real-model demo run" && git push
```

Render redeploys automatically and the banner switches to "Meta Model API".

## Settings (environment variables)

| Variable | Purpose |
|---|---|
| `MODEL_API_KEY` | Meta Model API key. Secret. |
| `APP_ACCESS_TOKEN` | Required for live runs and approvals. If unset (and not in mock mode) live runs are disabled. |
| `MOCK_LLM` | `1` runs scripted offline models. Never use on the real deployment. |
| `MAX_LIVE_RUNS_PER_DAY` | Rolling 24-hour cap on live runs (default 30). |
| `MIN_SECONDS_BETWEEN_RUNS` | Cooldown between live runs (default 10). |
| `REPLAY_FILE`, `RUN_DIR` | Recording to replay; where each live run's audit log is written. |
| `PORT` | Set by the host. |

## Rules that matter

- **Run exactly one instance.** Run state is in memory. Do not enable autoscaling or add instances.
- **Disk is ephemeral.** Audit logs in `data/runs/` disappear on redeploy. Download anything you want to keep, or add a database (see the production-readiness list).
- **Never commit `.env`.** The repo is public. If a key ever lands in git, revoke it in the Meta dashboard immediately.
- **Contributor models** (`*-contributor`) let Meta train on your prompts. Fine for simulated data only.
- **Streaming:** the live view uses Server-Sent Events. Any host or proxy must allow long-lived responses (over 60 seconds) and not buffer them.

## Other hosts

Any Docker host works (Fly.io, Railway, Google Cloud Run, a VM). Build the `Dockerfile`, set the environment variables above, and keep it to one instance. On Cloud Run, also raise the request timeout and keep minimum instances at 1 with CPU always allocated, or streams will drop and the process will be throttled between requests.
