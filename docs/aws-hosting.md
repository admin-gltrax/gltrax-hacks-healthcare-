# AWS hosting

## Live: Lightsail container service (2026-10-27)

**URL:** https://swarm-scheduler.72q91gp7bkhmc.us-west-2.cs.amazonlightsail.com/

Separate from gltrax.com: nothing in `gltrax-cluster`, `gltrax-alb` or the website's build was touched.

| Resource | Name | Notes |
|---|---|---|
| Lightsail container service | `swarm-scheduler` | `micro` (0.25 vCPU, 1 GB), 1 node, $10/month. Health check `/healthz`. Pulls from ECR through its private-registry role. |
| ECR repository | `swarm-scheduler` | Scan on push; keeps the last 10 images. Images are tagged with the short commit. |
| CodeBuild project | `swarm-scheduler-build` | Builds the `Dockerfile` from an S3 source zip (there is no Docker in the cloud dev environment). |
| S3 bucket | `swarm-scheduler-build-<account>` | Source zips only; private; objects expire after 30 days. |
| IAM role | `swarm-scheduler-codebuild-role` | Logs for this project, read the bucket, push to this ECR repo only. |

All are tagged `project=swarm-scheduler`. Expected cost: about $10/month for Lightsail plus cents for builds, storage and logs. Meta Model API usage for live runs is billed separately and capped by `MAX_LIVE_RUNS_PER_DAY`.

### Turning on live runs

The service starts with public replay and the provider directory only. To enable live swarms and voice intake, add two environment variables in the Lightsail console (Container services → `swarm-scheduler` → Deployments → Modify your deployment → container `app`):

- `MODEL_API_KEY`: the Meta Model API key.
- `APP_ACCESS_TOKEN`: a long random string; people type it into the dashboard to start live runs.

Saving creates a new deployment (about 3 minutes). Lightsail environment variables are visible to anyone with console access to the account.

### Redeploying

```bash
python scripts/deploy_lightsail.py   # builds HEAD in CodeBuild, deploys it, waits until live
```

Only committed code is deployed. Environment variables already on the service, including the two above, are carried over. A failed deployment leaves the previous version serving.

### Tearing down

Delete the Lightsail service (stops the $10/month), then the ECR repo, CodeBuild project, S3 bucket and IAM role listed above.

---

## Alternative considered: ECS next to gltrax.com (not built)

> Not built; the Lightsail service above was chosen instead (cheaper, no DNS work, no change to the shared ALB). Kept for reference.

## What exists in the GLTrax AWS account (us-west-2, checked 2026-10-27, read-only)

- `gltrax.com` runs as an ECS Fargate service `gltrax-website` (1 task, 0.5 vCPU / 1 GB) on cluster `gltrax-cluster`.
- It sits behind the internet-facing ALB `gltrax-alb`: port 80 redirects to 443; 443 forwards everything to the website by default. ALB idle timeout is 60 s.
- ACM certificate covers `gltrax.com` and `www.gltrax.com` only.
- Tasks run in private subnets with a NAT gateway, so outbound calls to `api.meta.ai` work.
- Images are built by CodeBuild (`gltrax-website-build`) into ECR (`gltrax-website`); secrets live in Secrets Manager (`gltrax/website/prod`).
- DNS for `gltrax.com` is **not** in Route 53; records are added at the external DNS provider.

## Recommended plan: `swarm.gltrax.com` next to the website

1. **ECR + CodeBuild.** New repo `swarm-scheduler` and a CodeBuild project that builds the existing `Dockerfile` (no local Docker needed).
2. **Secrets Manager.** Secret `gltrax/swarm-scheduler/prod` with `MODEL_API_KEY` (the real Meta key, entered by the owner in the console, never committed) and `APP_ACCESS_TOKEN` (long random string; gates live runs).
3. **ECS Fargate service** `swarm-scheduler` on `gltrax-cluster`:
   - exactly **1 task**, 0.5 vCPU / 1 GB, container port 8000, health check `/healthz`;
   - deployment `minimumHealthyPercent=0`, `maximumPercent=100`, so two copies never run at once (run state is in memory; see the `Dockerfile` comment);
   - env as in `render.yaml`: `MOCK_LLM=0`, `HOLD_SCALE=0.02`, `MAX_LIVE_RUNS_PER_DAY=30`, `MIN_SECONDS_BETWEEN_RUNS=10`;
   - reuse `gltrax-ecs-execution-role` (it needs read access to the new secret), private subnets, and a security group that only admits the ALB.
4. **ALB.** New target group (IP type, port 8000, health check `/healthz`) and a host-header rule `swarm.gltrax.com` → that target group on the 443 listener. The website's default action is untouched. This is a change to the production ALB, so get sign-off first.
5. **TLS + DNS.** Request an ACM certificate for `swarm.gltrax.com` and add it to the 443 listener. At the DNS provider, add two CNAMEs: the ACM validation record, and `swarm` → the ALB's DNS name.

SSE works through the ALB: the server sends a keepalive every 15 s, under the 60 s idle timeout.

Estimated cost: about $18/month for the Fargate task; the ALB and NAT gateway already exist.
