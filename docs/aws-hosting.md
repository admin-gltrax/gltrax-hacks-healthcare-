# AWS hosting (paused)

> **Status.** Planned, not started. Nothing has been created in AWS for this app. Render (`render.yaml`, [DEPLOY.md](../DEPLOY.md)) remains the documented way to host it.

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

## Alternative: Lightsail Containers

HTTPS URL on an AWS domain with no DNS work, about $10/month (micro, 1 GB), fully separate from the website. Same image from ECR, one node, same env and secrets. Use this if a `gltrax.com` subdomain or the shared ALB change isn't wanted.

## Open decisions before resuming

1. Sign-off to add a rule and certificate to the shared `gltrax-alb`.
2. Subdomain (`swarm.gltrax.com` proposed) and who adds the two CNAMEs.
3. The owner puts the Meta API key into Secrets Manager.
