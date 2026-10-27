# Hosting guide

The app is one container running one process. Anyone with the URL can watch a **recorded replay** (free, no credentials). **Live runs** spend Meta Model API credits, so they require an access token.

## Deploy on AWS Lightsail (automatic on every merge to main)

The live demo runs on a Lightsail container service named `swarm-scheduler` in `us-west-2`. `.github/workflows/deploy.yml` redeploys it every time CI passes on `main`.

The workflow does four things:

1. Builds the Docker image.
2. Pushes the image to the service.
3. Creates a new deployment that keeps the service's current environment variables, port and health check, changing only the image.
4. Waits until `/healthz` answers.

App secrets such as `MODEL_API_KEY` stay in Lightsail and never pass through GitHub. To change a setting, edit it in the Lightsail console (**Deployments → Modify your deployment**); the next automatic deploy keeps it.

**One-time setup**

1. **Make sure the service has been deployed once** in the Lightsail console, with one container, its environment variables, and a public endpoint on port 8000 with health check path `/healthz`.

2. **In AWS IAM, create a user for GitHub**, for example `github-lightsail-deploy`, with only this policy:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "lightsail:GetContainerServices",
         "lightsail:GetContainerImages",
         "lightsail:RegisterContainerImage",
         "lightsail:CreateContainerServiceRegistryLogin",
         "lightsail:CreateContainerServiceDeployment"
       ],
       "Resource": "*"
     }]
   }
   ```

   Then create an access key for that user.

3. **Add the key to GitHub.** In this repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Never paste keys into chat, issues or code.

4. **Run the first deploy.** Go to **Actions → deploy → Run workflow**, or merge anything to `main`.

**Optional repository variables**

These go under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Default | Use |
|---|---|---|
| `LIGHTSAIL_SERVICE` | `swarm-scheduler` | Container service name |
| `LIGHTSAIL_REGION` | `us-west-2` | Region |
| `AWS_ROLE_ARN` | (unset) | Use GitHub OIDC with an IAM role instead of access keys. When this is set, the key secrets are not used. |

Until credentials are added, the workflow skips with a notice rather than failing.
AWS hosting (ECS Fargate next to gltrax.com) is planned but paused; see [docs/aws-hosting.md](docs/aws-hosting.md).

## Deploy on Render (about 10 minutes)

1. Sign in at render.com and connect your GitHub account.
2. **New > Blueprint**, choose this repository. Render reads `render.yaml`.
3. When prompted, paste your `MODEL_API_KEY` (Meta Model API key). It is stored by Render and never committed.
4. Apply. The first build takes a few minutes. The health check is `/healthz`.
5. Open the service URL. Click **Replay recorded run** to confirm it works.
6. For live runs, copy `APP_ACCESS_TOKEN` from the service's **Environment** tab (Render generated it), paste it into the token box on the dashboard, and click **Start live swarm**. Share the token only with your teammates.

`plan: starter` is a paid instance: free instances sleep when idle, so the first visitor (or a judge) would wait through a cold start. Check Render's current pricing before applying.

## The public replay

`recordings/demo.jsonl` is a live run on the Meta Model API (`muse-spark-1.3` for the agent and the simulated offices, recorded 2026-10-27): 15/15 calls succeeded, 15/15 passed safety, and the best slot (Nov 2, 10:00) was won by honest leverage. To record a new one after changing prompts or scenarios:

```bash
python scripts/make_recording.py        # real models; writes recordings/demo.jsonl
# review it on the dashboard, then
git add recordings/demo.jsonl && git commit -m "Re-record demo run" && git push
```

Render redeploys automatically.

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
