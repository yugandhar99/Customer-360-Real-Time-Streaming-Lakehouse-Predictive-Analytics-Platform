# AWS data-layer deployment plan (pending approval)

**Status:** Locally validated. **Not deployed.** Waiting for AWS CLI auth as `customer360-deployer` and your explicit apply approval.

| Item | Value |
| --- | --- |
| Account | `783764597826` |
| Region | `us-east-1` |
| Intended identity | `customer360-deployer` |
| Terraform root | `infra/` |
| Proposed bucket | `customer360-783764597826-dev-data` |
| Firehose stream | `customer360-dev-events` |
| Glue database | `customer_360` |
| Athena workgroup | `customer360-dev-analytics` |
| EKS / NAT / VPC / ECR | **disabled** |

## Blocker: AWS CLI and identity

On this workstation:

- `aws` is **not installed**
- No `.aws` profile was found
- `aws sts get-caller-identity` **could not run**

### Secure setup (owner / deployer)

1. Install [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) (needs free disk on `C:`).
2. Authenticate as **`customer360-deployer`** via IAM Identity Center SSO or IAM user access keys stored only in the local credential store — **never root**, never paste keys into chat or git.
3. Confirm:

```powershell
$env:AWS_PROFILE = "customer360-dev"   # or the profile you created
$env:AWS_REGION = "us-east-1"
aws sts get-caller-identity
# Account must be 783764597826
.\.venv\Scripts\python.exe scripts\aws_preflight.py --check-identity
```

4. Attach (or assume a role that has) deploy permissions for S3, Firehose, Glue, Athena, IAM (project-prefixed roles + `iam:PassRole` for the Firehose role), CloudWatch Logs/Alarms, and optional Budgets. After apply, attach Terraform output `analytics_policy_arn` to the runtime identity for PutRecord + Athena.

## Resources Terraform will create (data layer only)

| Resource | Name / pattern | Billable |
| --- | --- | --- |
| S3 data bucket | `customer360-783764597826-dev-data` | Yes |
| S3 log bucket | `customer360-783764597826-dev-data-logs` | Yes |
| Firehose stream | `customer360-dev-events` | Per GB ingested |
| IAM role | `customer360-dev-firehose` | No |
| IAM policy | `customer360-dev-analytics` (includes `firehose:PutRecord`) | No |
| Glue database | `customer_360` | Free at small scale |
| Glue tables | `events` + metric tables | Free at small scale |
| Athena workgroup | `customer360-dev-analytics` (1 GiB scan cutoff) | Per TB scanned |
| CloudWatch log groups / alarms / dashboard | `/customer360/dev/...` | Low |
| Budget | only if `budget_email` set | Negligible |
| ECR / EKS / VPC / NAT | **not created** | — |

Public access: blocked on buckets. Encryption: SSE-S3 (AES256). Versioning: enabled on the data bucket. `force_destroy`: false.

## Cost estimate (not a quote)

Assumptions for first-month **dev synthetic** traffic: &lt;100k small events, &lt;1 GB S3, &lt;20 Athena queries scanning &lt;10 GB total, dashboard local, EKS/ECR/NAT off.

| Category | Rough monthly |
| --- | --- |
| S3 + requests | &lt; $1 |
| Firehose | &lt; $1 |
| Athena | ~$0.05 if 10 GB scanned |
| Glue catalog | $0 |
| CloudWatch | &lt; $1 |
| **Total** | **about $2–5** |

Alerts do **not** hard-stop spend. Leaving Athena queries unscoped or enabling EKS later changes this sharply (~+$73/mo control plane).

## Commands after identity works (still wait for apply approval)

```powershell
D:\c360-tools\terraform\terraform.exe -chdir=infra fmt -check -recursive
D:\c360-tools\terraform\terraform.exe -chdir=infra init -backend=false -input=false
D:\c360-tools\terraform\terraform.exe -chdir=infra validate
D:\c360-tools\terraform\terraform.exe -chdir=infra plan -out=tfplan
# Review plan + cost with owner → only then:
# D:\c360-tools\terraform\terraform.exe -chdir=infra apply tfplan
```

## Approval checklist (reply in chat)

Reply with something like:

1. `APPROVE APPLY` for account `783764597826` / `us-east-1`
2. Confirm bucket name `customer360-783764597826-dev-data` (or give another unique name)
3. Confirm EKS/ECR/NAT stay **off**
4. Optional budget email
5. Confirm estimated **$2–5/mo** for light synthetic use is accepted

Until that message, **no apply will run**.
