#!/usr/bin/env bash
# Runs the parameter sweep on a transient Amazon EMR cluster that terminates
# when the step finishes. Prerequisites: `terraform apply` in infra/aws, AWS SSO
# credentials in the environment, and `make data forecast` locally.
#
#   infra/emr/submit_sweep.sh <bucket> [core-node-count]
set -euo pipefail
bucket=${1:?usage: submit_sweep.sh BUCKET [CORE_NODES]}
nodes=${2:-4}
root=$(cd "$(dirname "$0")/../.." && pwd)

# EMR's system Python is older than the project's 3.12, so the job ships its own
# Linux Python 3.12 environment (with the compiled engine module) as an archive.
docker build -f "$root/infra/Dockerfile.gateway" -t microprice-gateway "$root"
docker run --rm -v /tmp/microprice-release:/out microprice-gateway \
  sh -c "cd /app/research && tar -czf /out/pyenv.tar.gz -C .venv . && cp -r microprice /out/"
(cd /tmp/microprice-release && zip -qr microprice.zip microprice)
aws s3 cp /tmp/microprice-release/pyenv.tar.gz "s3://$bucket/release/pyenv.tar.gz"
aws s3 cp /tmp/microprice-release/microprice.zip "s3://$bucket/release/microprice.zip"
aws s3 cp "$root/sweeps/run_sweep.py" "s3://$bucket/release/run_sweep.py"
aws s3 sync "$root/data/sessions" "s3://$bucket/sessions"

aws emr create-cluster \
  --name microprice-sweep \
  --release-label emr-7.3.0 \
  --applications Name=Spark \
  --service-role microprice-emr-service \
  --ec2-attributes InstanceProfile=microprice-emr-nodes \
  --instance-groups InstanceGroupType=MASTER,InstanceCount=1,InstanceType=m6i.xlarge \
                    InstanceGroupType=CORE,InstanceCount="$nodes",InstanceType=c6i.4xlarge \
  --log-uri "s3://$bucket/emr-logs/" \
  --auto-terminate \
  --steps Type=Spark,Name=sweep,ActionOnFailure=TERMINATE_CLUSTER,Args=[\
--deploy-mode,cluster,--archives,s3://$bucket/release/pyenv.tar.gz#pyenv,\
--conf,spark.pyspark.python=./pyenv/bin/python,--py-files,s3://$bucket/release/microprice.zip,\
s3://$bucket/release/run_sweep.py,--sessions,s3://$bucket/sessions,--out,s3://$bucket/results/sweeps/sweep.parquet]
