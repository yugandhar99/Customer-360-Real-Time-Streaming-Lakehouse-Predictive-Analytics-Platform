"""Local AWS readiness checks. Never creates or modifies cloud resources.

Offline mode (default): files, tools, and configuration only.
Authenticated mode: read-only STS identity check against the target account.

Usage:
  python scripts/aws_preflight.py
  python scripts/aws_preflight.py --check-identity
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_ACCOUNT = "783764597826"
TARGET_REGION = "us-east-1"
PLACEHOLDER = "__SET_AFTER_AWS_ACCESS__"

REQUIRED_FILES = (
    "config.py",
    ".env.example",
    "infra/main.tf",
    "infra/variables.tf",
    "infra/outputs.tf",
    "infra/terraform.tfvars.example",
    "infra/modules/iam/main.tf",
    "infra/modules/firehose/main.tf",
    "infra/modules/s3/main.tf",
    "infra/modules/glue/main.tf",
    "infra/modules/athena/main.tf",
    "ingestion/firehose_publisher.py",
    "storage/athena_backend.py",
    "aws_sql/ltv.sql",
    "requirements.txt",
)

TERRAFORM_OUTPUT_ENV = (
    "AWS_S3_BUCKET",
    "AWS_FIREHOSE_STREAM",
    "ATHENA_WORKGROUP",
    "ATHENA_RESULTS_S3_URI",
)


def _ok(message: str) -> None:
    print(f"[OK]   {message}")


def _warn(message: str) -> None:
    print(f"[WARN] {message}")


def _fail(message: str) -> None:
    print(f"[FAIL] {message}")


def _unresolved(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
    return not text or PLACEHOLDER in text


def check_project_files() -> bool:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        for path in missing:
            _fail(f"Missing project file: {path}")
        return False
    _ok(f"Required project files present ({len(REQUIRED_FILES)})")
    return True


def check_iam_put_record() -> bool:
    policy = (ROOT / "infra/modules/iam/main.tf").read_text(encoding="utf-8")
    if "firehose:PutRecord" in policy and "PublishEventsToFirehose" in policy:
        _ok("Terraform analytics policy includes firehose:PutRecord")
        return True
    _fail("Terraform analytics policy is missing firehose:PutRecord")
    return False


def check_cli_tools() -> bool:
    aws = shutil.which("aws")
    terraform = shutil.which("terraform")
    local_tf = Path(os.environ.get("TEMP", "")) / "c360-tools" / "terraform" / "terraform.exe"
    d_tf = Path("D:/c360-tools/terraform/terraform.exe")
    if aws:
        _ok(f"AWS CLI found: {aws}")
    else:
        _warn("AWS CLI not found on PATH (required only after access is granted)")
    if terraform:
        _ok(f"Terraform found: {terraform}")
        return True
    for candidate in (d_tf, local_tf):
        if candidate.exists():
            _ok(f"Terraform found: {candidate}")
            return True
    _warn("Terraform not found on PATH (install before plan/apply)")
    return True


def check_environment() -> bool:
    mode = os.getenv("EXECUTION_MODE", "local").strip().lower()
    region = os.getenv("AWS_REGION", TARGET_REGION).strip()
    account = os.getenv("AWS_ACCOUNT_ID", TARGET_ACCOUNT).strip()
    profile = os.getenv("AWS_PROFILE", "").strip()
    use_gcp = os.getenv("USE_GCP", "false").strip().lower()

    _ok(f"EXECUTION_MODE={mode}")
    if region != TARGET_REGION:
        _warn(f"AWS_REGION is {region!r}; target documentation uses {TARGET_REGION}")
    else:
        _ok(f"AWS_REGION={region}")
    if account != TARGET_ACCOUNT:
        _warn(f"AWS_ACCOUNT_ID is {account!r}; expected {TARGET_ACCOUNT}")
    else:
        _ok(f"AWS_ACCOUNT_ID={account}")
    if profile:
        _ok(f"AWS_PROFILE={profile}")
    else:
        _warn("AWS_PROFILE is unset (set customer360-dev after access is configured)")

    unresolved = [name for name in TERRAFORM_OUTPUT_ENV if _unresolved(os.getenv(name))]
    if mode == "aws":
        if use_gcp in {"1", "true", "yes", "on"}:
            _fail("USE_GCP must be false when EXECUTION_MODE=aws")
            return False
        if unresolved:
            for name in unresolved:
                _fail(f"{name} still unresolved (replace {PLACEHOLDER})")
            return False
        _ok("AWS mode environment variables are resolved")
        return True

    if unresolved:
        _warn(
            "Terraform-output placeholders still unresolved "
            f"({', '.join(unresolved)}); fine while EXECUTION_MODE=local"
        )
    else:
        _ok("AWS resource identifiers are set")
    return True


def check_tfvars_placeholder() -> bool:
    example = ROOT / "infra/terraform.tfvars.example"
    text = example.read_text(encoding="utf-8")
    if "set-after-aws-access" in text or PLACEHOLDER in text:
        _ok("terraform.tfvars.example still uses a bucket placeholder (expected before access)")
    tfvars = ROOT / "infra/terraform.tfvars"
    if tfvars.exists():
        body = tfvars.read_text(encoding="utf-8")
        if PLACEHOLDER in body:
            _warn("infra/terraform.tfvars still contains unresolved placeholders")
        else:
            _ok("infra/terraform.tfvars exists and has no placeholder marker")
    else:
        _warn("infra/terraform.tfvars not created yet (copy from terraform.tfvars.example)")
    return True


def check_identity() -> bool:
    aws = shutil.which("aws")
    if not aws:
        _fail("Cannot check identity: AWS CLI is not installed")
        return False
    env = os.environ.copy()
    profile = env.get("AWS_PROFILE", "").strip()
    command = [aws, "sts", "get-caller-identity", "--output", "json"]
    if profile:
        command.extend(["--profile", profile])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    except OSError as exc:
        _fail(f"Identity check failed to start: {exc}")
        return False
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip().splitlines()
        _fail(f"Identity check failed: {detail[0] if detail else 'unknown error'}")
        return False
    # Avoid printing the full JSON (may include account/user). Parse Account only.
    account = ""
    region = env.get("AWS_REGION", TARGET_REGION)
    for line in completed.stdout.splitlines():
        if '"Account"' in line:
            account = line.split(":")[-1].strip().strip(',').strip('"')
    if not account:
        _fail("Identity check returned no Account field")
        return False
    if account != TARGET_ACCOUNT:
        _fail(f"Authenticated account {account} does not match {TARGET_ACCOUNT}")
        return False
    _ok(f"Authenticated account matches {TARGET_ACCOUNT}")
    if region != TARGET_REGION:
        _warn(f"AWS_REGION is {region}; expected {TARGET_REGION} for this project")
    else:
        _ok(f"Configured region is {TARGET_REGION}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Customer 360 AWS preflight (no provisioning).")
    parser.add_argument(
        "--check-identity",
        action="store_true",
        help="Run a read-only STS GetCallerIdentity check with the configured profile.",
    )
    args = parser.parse_args(argv)

    print("Customer 360 AWS preflight")
    print(f"Project root: {ROOT}")
    print(f"Target account: {TARGET_ACCOUNT}  region: {TARGET_REGION}")
    print("Mode: authenticated identity check" if args.check_identity else "Mode: offline")
    print("-" * 60)

    ok = True
    ok = check_project_files() and ok
    ok = check_iam_put_record() and ok
    check_cli_tools()
    ok = check_environment() and ok
    check_tfvars_placeholder()

    if args.check_identity:
        ok = check_identity() and ok
    else:
        _ok("Skipped AWS API calls (pass --check-identity after access is configured)")

    print("-" * 60)
    if ok:
        print("RESULT: READY for local work / pending owner access for deploy")
        return 0
    print("RESULT: NOT READY — fix FAIL items above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
