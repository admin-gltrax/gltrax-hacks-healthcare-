"""Build the committed code and deploy it to the Lightsail container service.

    python scripts/deploy_lightsail.py            # build HEAD, deploy, wait until live

Steps: `git archive HEAD` -> S3 -> CodeBuild (docker build, push to ECR, tagged
with the short commit) -> new Lightsail deployment of that image. Environment
variables already set on the service (MODEL_API_KEY, APP_ACCESS_TOKEN, ...) are
carried over, so secrets entered in the Lightsail console survive redeploys.
Needs AWS credentials with access to the resources in docs/aws-hosting.md.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import boto3

REGION = "us-west-2"
SERVICE = "swarm-scheduler"
REPO = "swarm-scheduler"
PROJECT = "swarm-scheduler-build"
DEFAULT_ENV = {"MOCK_LLM": "0", "HOLD_SCALE": "0.02", "MAX_LIVE_RUNS_PER_DAY": "30", "MIN_SECONDS_BETWEEN_RUNS": "10", "PORT": "8000"}
ROOT = Path(__file__).resolve().parents[1]


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def build(sha: str, acct: str) -> str:
    if sh("git", "status", "--porcelain", "--untracked-files=no"):
        print("note: uncommitted changes are not deployed; only HEAD is built")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "source.zip"
        sh("git", "archive", "--format=zip", "-o", str(zip_path), "HEAD")
        boto3.client("s3", region_name=REGION).upload_file(str(zip_path), f"swarm-scheduler-build-{acct}", "source.zip")
    cb = boto3.client("codebuild", region_name=REGION)
    b = cb.start_build(projectName=PROJECT, environmentVariablesOverride=[{"name": "IMAGE_TAG", "value": sha, "type": "PLAINTEXT"}])["build"]
    print(f"building {sha} ({b['id']})")
    while (b := cb.batch_get_builds(ids=[b["id"]])["builds"][0])["buildStatus"] == "IN_PROGRESS":
        time.sleep(10)
    if b["buildStatus"] != "SUCCEEDED":
        sys.exit(f"build {b['buildStatus']}: see CodeBuild logs for {b['id']}")
    return f"{acct}.dkr.ecr.{REGION}.amazonaws.com/{REPO}:{sha}"


def deploy(image: str) -> str:
    ls = boto3.client("lightsail", region_name=REGION)
    svc = ls.get_container_services(serviceName=SERVICE)["containerServices"][0]
    current = (svc.get("currentDeployment") or {}).get("containers", {}).get("app", {})
    env = {**DEFAULT_ENV, **current.get("environment", {})}  # keep secrets set in the console
    ls.create_container_service_deployment(
        serviceName=SERVICE,
        containers={"app": {"image": image, "ports": {"8000": "HTTP"}, "environment": env}},
        publicEndpoint={"containerName": "app", "containerPort": 8000, "healthCheck": {
            "path": "/healthz", "successCodes": "200", "intervalSeconds": 10, "timeoutSeconds": 5,
            "healthyThreshold": 2, "unhealthyThreshold": 3}},
    )
    print(f"deploying {image}")
    while True:
        svc = ls.get_container_services(serviceName=SERVICE)["containerServices"][0]
        nxt, cur = svc.get("nextDeployment") or {}, svc.get("currentDeployment") or {}
        if nxt.get("state") == "FAILED":
            sys.exit("deployment FAILED; the previous version keeps serving. Check the container logs in Lightsail.")
        if not nxt and cur.get("containers", {}).get("app", {}).get("image", "").endswith(image.split("/")[-1]) and cur.get("state") == "ACTIVE":
            return svc["url"]
        time.sleep(15)


def main() -> None:
    acct = boto3.client("sts").get_caller_identity()["Account"]
    url = deploy(build(sh("git", "rev-parse", "--short", "HEAD"), acct))
    print(f"live: {url}")


if __name__ == "__main__":
    main()
