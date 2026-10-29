# Customer 360 Real-Time Analytics and Predictive Intelligence Platform

The platform generates synthetic ecommerce events, stores them, and calculates lifetime value, funnel, retention, cohort, segmentation, and churn metrics. A Flask dashboard renders those metrics.

Local SQLite is the default execution mode. AWS resources are defined and the application can target Athena when configuration is complete. The original GCP Pub/Sub and BigQuery modules are still in the repository and stay disabled unless `EXECUTION_MODE=gcp`.

No live AWS or GCP account was contacted during this implementation. Terraform was validated locally and was not applied.

## Architecture

```text
Local mode
  event generator -> CSV -> SQLite -> pandas analytics -> Flask

AWS mode, prepared and not yet provisioned
  event generator -> Firehose -> S3 raw/events/
  Glue catalog -> Athena workgroup -> pandas analytics and Flask
  metric tables written back to S3 analytics/
  dashboard container on EKS, with CloudWatch logs and alarms

Legacy GCP mode, preserved and disabled by default
  Pub/Sub -> BigQuery -> existing SQL and Airflow DAGs
```

Amazon Data Firehose is the ingestion service. Kinesis Data Streams was not added. Firehose buffers for 60 seconds or 1 MB, whichever comes first, then writes gzip JSON to:

```text
s3://<bucket>/raw/events/year=YYYY/month=MM/day=DD/
s3://<bucket>/raw/errors/<error-type>/year=YYYY/month=MM/day=DD/
s3://<bucket>/processed/events/
s3://<bucket>/analytics/<metric-table>/metrics.json
s3://<bucket>/athena-results/
s3://<bucket>/test-fixtures/
```

The year, month, and day prefixes are Firehose arrival time in UTC. The event timestamp inside each JSON record is what cohort SQL uses. Partition projection on the Glue `events` table avoids `MSCK REPAIR TABLE` for those keys.

Delivery is at least once, not exactly once. A retried publish sends the same `event_id` and the same JSON body. After Firehose accepts it, that process will not send the id again. A restarted process, or an internal Firehose retry, can still write a second object. Athena reads issued by the application collapse those copies with `row_number()` on `event_id` before LTV, funnel, retention, cohort, segmentation, and churn calculations. `aws_sql/events_deduped.sql` is the same rule for a query you run yourself. The local CSV loader still appends duplicate rows, because that file has no `event_id` column and the existing local contract keeps both rows.

## Technology stack

- Python 3.11, Flask, pandas, scikit-learn
- SQLite for local execution
- Amazon S3, Data Firehose, Glue Data Catalog, Athena, IAM, ECR, EKS, CloudWatch, and an optional VPC and budget
- Docker, Terraform, Kubernetes, GitHub Actions
- Ruff and unittest

## Prerequisites

- Python 3.11
- The existing virtual environment at `.venv`
- Docker Desktop, only when building the image
- Terraform 1.5 or newer, only when checking or applying infrastructure
- kubectl and an authorized EKS cluster, only when deploying

Do not put access keys in source files. Use an IAM role, a named AWS profile, or environment variables supplied outside the repository.

## Local Python setup

From PowerShell, in the project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`.env` is not loaded automatically. Set variables in the shell when you need them. The defaults are already local SQLite:

```powershell
$env:EXECUTION_MODE = "local"
$env:LOCAL_BACKEND = "sqlite"
$env:AWS_ENABLED = "false"
$env:USE_GCP = "false"
$env:FLASK_DEBUG = "false"
```

## SQLite workflow

Generate a few synthetic events, load them, calculate metrics, and open the dashboard.

```powershell
.\.venv\Scripts\python.exe -c "from ingestion.event_generator import EventGenerator; g = EventGenerator();
from ingestion.publisher import LocalCsvEventSink; g.sink = LocalCsvEventSink();
[g.sink.publish(g.generate_single_event()) for _ in range(20)]"
.\.venv\Scripts\python.exe processing\data_loader.py
.\.venv\Scripts\python.exe transformations\ltv_analysis.py
.\.venv\Scripts\python.exe transformations\funnel_analysis.py
.\.venv\Scripts\python.exe transformations\retention_analysis.py
.\.venv\Scripts\python.exe transformations\cohort_analysis.py
.\.venv\Scripts\python.exe ml\churn_model.py
.\.venv\Scripts\python.exe ml\segmentation.py
.\.venv\Scripts\python.exe dashboard\app.py
```

The development server listens on port 5000 and does not enable debug unless `FLASK_DEBUG=true`. Open `http://127.0.0.1:5000`. Health is `http://127.0.0.1:5000/health`.

Local SQLite and model files are stored on the C drive at `C:\Customer360\storage`. Override that with `STORAGE_DIR` or `SQLITE_DB_PATH`. `processing/data_loader.py` reads `logs/raw_events.csv` and appends into `customer_360.db` in that folder. It then truncates the CSV back to its header. Do not point it at a file you need to keep.

## Churn definition

`CHURN_RULE=heuristic` is the default. A user is at risk when `event_count` is 2 or less and `purchase_count` is 0. Set `CHURN_RULE=inactivity` to use `CHURN_INACTIVITY_THRESHOLD_DAYS` instead. In that mode the reference time is the latest event in the dataset, and a user is at risk when their own last event is more than that many days earlier. The default was not changed, so existing dashboard numbers stay stable.

Segmentation still writes `segmentation_kmeans.pkl` in `C:\Customer360\storage` as a scikit-learn model. It also writes `segmentation_bundle.joblib` there, containing the model and the fitted scaler. Loading prefers the bundle and falls back to the legacy pickle.

## Docker

Docker Desktop was not installed on the machine used for this implementation, so the image was not built or run here. Install it from the Docker Desktop for Windows documentation, start Docker Desktop, and confirm `docker version` prints a server version before using the commands below. Docker Desktop needs several gigabytes free on the system drive; free space on `C:` before installing if that drive is nearly full. The container command is Gunicorn, not the Flask debugger. It binds to `0.0.0.0` and `${PORT:-5000}` with one worker, so SQLite is not shared across worker processes. The process user is uid 1000. The image does not copy `.env`, the virtual environment, SQLite files, logs, or model artifacts. Compose bind-mounts `C:\Customer360\storage` at `/app/storage`, so a container restart keeps that database on the C drive.

```powershell
docker build -t customer360-dashboard:local .
docker compose up --build
docker compose down
```

The analytics profile runs the metric jobs against the same SQLite volume. It exits after one run:

```powershell
docker compose --profile analytics up --build
```

If a bind mount is used instead of the named volume, the non-root user may not be able to write to it. The Dockerfile health check calls `/health` on `127.0.0.1` and the container `PORT`, which defaults to 5000. Compose uses the same port.

Troubleshooting:

- The image fails at startup with `AWS execution requires configuration` when `EXECUTION_MODE=aws` and the bucket, workgroup, or result URI is empty. Fill those variables or switch back to `EXECUTION_MODE=local`.
- Port 5000 is already in use. Stop the other process or change the compose port mapping.
- Health stays failing. Read `docker compose logs dashboard` and confirm Gunicorn bound to `0.0.0.0:5000`.

## AWS migration guide

Target account: `783764597826`. Target region: `us-east-1`. Project/environment names: `customer360` / `dev`.

Data path: events → Firehose → S3 → Glue Data Catalog → Athena → analytics metrics / local Flask dashboard.

GCP Pub/Sub and BigQuery modules remain in the repository for rollback. They stay disabled unless `EXECUTION_MODE=gcp`. Dashboard hosting on EKS is optional and **disabled by default**.

### Architecture overview

```text
Publisher (Python) --PutRecord--> Firehose --gzip JSON--> S3 raw/events/year=/month=/day=/
Glue external table "events" (partition projection)
Athena workgroup (1 GiB scan cutoff) --> pandas analytics --> S3 analytics/<table>/
Flask dashboard reads Athena in EXECUTION_MODE=aws (no SQLite fallback)
```

### Local prerequisites

- Python 3.11 and `.venv`
- Terraform 1.5+ for plan/validate (apply only after approval)
- AWS CLI only after the account owner grants access
- Docker is optional and not required for the data-layer migration

### Run the dashboard locally (no AWS)

```powershell
$env:EXECUTION_MODE = "local"
$env:AWS_ENABLED = "false"
$env:USE_GCP = "false"
$env:LOG_TO_FILE = "false"
.\.venv\Scripts\python.exe dashboard\app.py
```

Open `http://127.0.0.1:5000` and `http://127.0.0.1:5000/health`.

### Offline AWS readiness check

```powershell
.\.venv\Scripts\python.exe scripts\aws_preflight.py
```

### Configure the AWS CLI after access is granted

Use the IAM identity **`customer360-deployer`** (or another approved deployer). Never use the account root password in the CLI.

```powershell
# Install AWS CLI v2 first if `aws --version` fails.
aws configure sso
# or: aws configure --profile customer360-dev
$env:AWS_PROFILE = "customer360-dev"
$env:AWS_REGION = "us-east-1"
$env:AWS_ACCOUNT_ID = "783764597826"
aws sts get-caller-identity
# Account must equal 783764597826
.\.venv\Scripts\python.exe scripts\aws_preflight.py --check-identity
```

Do not paste access keys into the repository or into chat. See `docs/AWS_DEPLOYMENT_PLAN.md` for the pending apply checklist.

### Copy environment placeholders

`.env.example` documents both local defaults and AWS placeholders. The process environment is what the app reads; `.env` is not loaded automatically.

Replace every `__SET_AFTER_AWS_ACCESS__` value with Terraform outputs after an authorized apply:

| Variable | Source |
| --- | --- |
| `AWS_S3_BUCKET` | `terraform output s3_bucket_name` |
| `AWS_FIREHOSE_STREAM` | `terraform output firehose_stream_name` (expected `customer360-dev-events`) |
| `ATHENA_WORKGROUP` | `terraform output athena_workgroup_name` (expected `customer360-dev-analytics`) |
| `ATHENA_RESULTS_S3_URI` | `terraform output athena_results_s3_uri` |
| `AWS_GLUE_DATABASE` | usually `customer_360` (stable) |
| `AWS_REGION` | `us-east-1` (stable) |
| `AWS_ACCOUNT_ID` | `783764597826` (stable, not a credential) |
| `AWS_PROFILE` | owner-created profile, e.g. `customer360-dev` |

Placeholder strings are rejected when `EXECUTION_MODE=aws`. AWS analytics failures return HTTP 503 and do not open SQLite.

```powershell
$env:EXECUTION_MODE = "aws"
$env:AWS_ENABLED = "true"
$env:USE_GCP = "false"
$env:AWS_REGION = "us-east-1"
$env:AWS_S3_BUCKET = "<bucket-from-terraform-output>"
$env:AWS_FIREHOSE_STREAM = "<stream-from-terraform-output>"
$env:AWS_GLUE_DATABASE = "customer_360"
$env:ATHENA_WORKGROUP = "<workgroup-from-terraform-output>"
$env:ATHENA_RESULTS_S3_URI = "s3://<bucket>/athena-results/"
```

Aliases: `AWS_FIREHOSE_DELIVERY_STREAM`, `AWS_ATHENA_DATABASE`, `AWS_ATHENA_QUERY_RESULTS_LOCATION`.

### Terraform (no apply until approved)

The root module is `infra/`. It defines S3, Firehose, Glue, Athena, IAM (including scoped `firehose:PutRecord` for the analytics policy), CloudWatch, and an optional budget. VPC, NAT, EKS, and ECR stay off by default (`enable_ecr=false`) for the data-layer phase.

State is local by default (`infra/terraform.tfstate`). Do not commit state files. A remote S3 backend is recommended later but is **not** created automatically, because creating that backend itself needs AWS access.

```powershell
Copy-Item infra\terraform.tfvars.example infra\terraform.tfvars
# Set a globally unique bucket_name and optional budget_email.
# Keep enable_eks and enable_nat_gateway false for the first deploy.
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false -input=false
terraform -chdir=infra validate
terraform -chdir=infra plan -out=tfplan
```

**Stop for cost approval before apply.** After approval only:

```powershell
terraform -chdir=infra apply tfplan
terraform -chdir=infra output
```

### Live pipeline test (requires AWS)

1. Publish a synthetic batch with `EXECUTION_MODE=aws`.
2. Wait up to 60 seconds for Firehose buffering.
3. Confirm objects under `s3://<bucket>/raw/events/`.
4. In the Athena workgroup, run `aws_sql/ltv.sql` (or the app LTV job).
5. Run funnel, retention, cohort, churn, and segmentation jobs.
6. Open the local dashboard; KPIs must come from Athena.
7. Confirm a forced Athena failure returns HTTP 503 without SQLite data.

Live Firehose → S3 → Glue → Athena has **not** been executed from this workstation.

Athena SQL lives in `aws_sql/`. GCP SQL in `gcp_sql_models/` and `dbt_models/` was not rewritten. The workgroup enforces a 1 GiB scanned-data cutoff by default.

Synthetic events only. Do not upload real customer data during development.

Expected development cost with EKS and NAT left off, under 1 GB of events per month and under 10 GB scanned by Athena:

| Item | Assumption | Rough monthly cost |
| --- | --- | --- |
| S3 storage and requests | under 1 GB, versioning on | under 1 USD |
| Firehose | 0.029 USD per GB ingested | under 1 USD |
| Glue catalog | small number of tables | 0 USD |
| Athena | 5 USD per TB, 10 GB scanned | about 0.05 USD |
| CloudWatch logs | 14-day retention, low volume | under 1 USD |
| ECR | a few images | under 1 USD |
| VPC with no NAT | default | 0 USD |
| Budget | created only when an email is set | 0 USD |

Turning on EKS adds about 73 USD per month for the control plane, about 15 USD for one `t3.small` node, and about 32 USD more if the NAT gateway is enabled, before data transfer. Those switches stay false until a deployment is approved.

Cleanup, after an authorized apply:

```powershell
# Empty both buckets, including noncurrent versions, before destroy when force_destroy is false.
terraform -chdir=infra destroy
```

Rollback for the application is `EXECUTION_MODE=local`. That does not delete AWS data. Destroying infrastructure deletes the bucket only when it is empty or `force_destroy` is true.

## Kubernetes

Manifests in `k8s/base` run the dashboard in local mode. `k8s/aws` replaces the ConfigMap and service account and adds a nightly analytics job. S3, Athena, Glue, and Firehose are not run inside the cluster.

kubeconform 0.6.7 reported 8 valid resources for Kubernetes 1.29. Nothing was applied to a cluster.

```powershell
kubectl apply -f k8s/base
kubectl -n customer360 rollout status deployment/customer360-dashboard
kubectl -n customer360 port-forward svc/customer360-dashboard 8080:80
```

Before the AWS overlay, replace `ACCOUNT_ID` in `k8s/aws/serviceaccount.yaml` with the `analytics_role_arn` output and fill the empty AWS settings in `k8s/aws/configmap.yaml`. An empty bucket with `EXECUTION_MODE=aws` makes the process exit. That is intentional.

```powershell
kubectl apply -f k8s/aws
```

The local emptyDir volume is not shared with the analytics job. Use AWS mode for the CronJob so metrics are written to S3.

## CI/CD

`.github/workflows/ci.yml` checks out the code, installs Python 3.11 dependencies from `requirements-dev.txt`, runs Ruff and unittest, checks the default configuration, builds the image, runs Trivy as an informational scan, validates Terraform, and runs kubeconform. It does not need AWS credentials and it does not push an image.

`.github/workflows/deploy.yml` runs only from a manual dispatch when the input is `deploy`, and only after the GitHub `production` environment approves it. It assumes `vars.AWS_DEPLOY_ROLE_ARN` through GitHub OIDC. There are no access keys in the workflow. The workflow has not been executed.

This directory is not a git repository. Git was not initialized and no remote was created.

## Monitoring

Application logs are text by default and include a JSON payload from the Firehose and Athena components. Each of those lines has a timestamp, severity, component, and event or query id. Secret-like fields are dropped. Set `LOG_TO_FILE=false` to keep logs off `logs/platform.log`.

CloudWatch log groups, metric filters, and alarms are defined in Terraform. They are not receiving live traffic. The assumptions are:

- One Firehose error in five minutes is enough to alarm, because the publisher already retried.
- Delivery freshness above 900 seconds means the stream is stuck. Normal buffering is 60 seconds.
- Missing Firehose or query metrics do not alarm, so an idle development account stays quiet.
- Container health is the Kubernetes liveness probe on `/health`. Container Insights is not enabled.

The operations dashboard is created with the CloudWatch resources. It has no data until the stream and the application log group receive events. EKS must ship container stdout to `/customer360/<environment>/application` before the application metric filters can see failures.

Troubleshooting:

- Firehose delivery failed. Check `publisher.failed`, the Firehose error prefix under `raw/errors/`, and the Firehose log group. Confirm the delivery role can write only to `raw/*`.
- S3 has no new objects. The buffer may still be open for up to 60 seconds. Confirm the stream name and that `put_record` returned a record id.
- Glue or Athena says the table does not exist. Confirm `AWS_GLUE_DATABASE`, the bucket location, and that partition projection is enabled. Do not create a second table with the same name.
- Athena fails or scans too much. Read the query error in the application log. The workgroup stops a query above the byte cutoff. Narrow the partition prefix.
- The dashboard is empty in local mode. The metric tables have not been built, or the SQLite file is missing. The page stays available and shows zeros.
- The dashboard returns HTTP 503 in AWS mode when an analytics query fails. The JSON body says local data was not substituted and does not present zeros as metrics. `/health` still returns 200, because it only checks that the process is up. Fix the Athena error. Do not switch the process to SQLite to hide it.

## Tests

```powershell
$env:LOG_TO_FILE = "false"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\ruff.exe check config.py ingestion storage transformations processing ml dashboard utils aws_sql tests
```

The suite uses temporary databases, synthetic rows, and mocked AWS clients. It does not call AWS or GCP. The latest local run was 39 tests, all passing. Ruff reported no issues for those paths and for `python -m ruff check .`. Offline preflight: `python scripts/aws_preflight.py`.

`tests/test_phase3.py` originally expected AWS mode to raise `NotImplementedError`. It now expects a configuration error that names the missing settings and refuses a SQLite fallback. The other Phase 3 checks and the Phase 4 analytics contracts still pass. The contract tests also confirm the BigQuery SQL files still use their original dialect.

## Verification labels

| Integration | Label |
| --- | --- |
| Local SQLite pipeline, heuristic churn, dashboard, and `/health` | **Locally tested** |
| Inactivity churn rule, SQLite file close, and Athena event-id dedupe SQL | **Locally tested** |
| Firehose retry, Athena result mapping, and missing AWS configuration | **Mock-tested** |
| Dockerfile, Compose, Terraform, Kubernetes manifests, and GitHub workflow YAML | **Static validation passed** |
| Docker image build and container startup | **Not tested** — Docker is not installed in this environment |
| GitHub-hosted Actions run | **Not tested** |
| Live Firehose, S3, Glue, Athena, CloudWatch, ECR, and EKS | **Requires authorized AWS access** |

The project is not deployed on AWS.

## What is implemented, scaffolded, and unverified

| Area | State |
| --- | --- |
| Local SQLite pipeline, analytics, and dashboard | Implemented and covered by unittest |
| Event validation, local sink, Firehose publisher | Implemented; Firehose client is mocked, not live |
| Athena backend, SQL, result mapping, and event-id dedupe | Implemented; Athena and S3 clients are mocked, not live |
| Optional inactivity churn rule | Implemented behind `CHURN_RULE=inactivity`; default remains the heuristic |
| GCP Pub/Sub and BigQuery modules | Preserved, disabled by default, not deleted |
| Docker image | Dockerfile and Compose passed static checks; the image was not built because Docker is not installed |
| Terraform | `fmt -check`, `init -backend=false`, and `validate` succeeded; `apply` was not run |
| Kubernetes | kubeconform validated 8 manifests; no cluster deploy |
| GitHub Actions | Workflows are written and checked for manual production deploy; they have not run on GitHub |
| CloudWatch alarms and dashboard | Defined in Terraform; no live metrics |
| ECR publish and EKS rollout | Workflow exists and is manual; not executed |

## Authorized AWS deployment

1. Choose a unique bucket name and review `infra/terraform.tfvars`.
2. Run `terraform plan` and apply only after the cost is approved.
3. Export the Terraform outputs into the environment variables in the AWS section.
4. Publish a synthetic batch with `EXECUTION_MODE=aws` and confirm objects under `raw/events/`.
5. Run one Athena query from `aws_sql/ltv.sql` in the configured workgroup and compare it with the local fixture.
6. Build the image, push it to the ECR output, and set `enable_eks=true` only if the cluster cost is approved.
7. Replace the service-account role annotation, apply `k8s/aws`, and check `/health` from inside the pod.
8. Confirm CloudWatch receives stdout before relying on the ingestion and query alarms.
