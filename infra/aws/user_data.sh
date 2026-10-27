#!/bin/bash
# Installs Docker, pulls the release bundle and results from S3, and starts the stack.
set -euo pipefail
dnf install -y docker
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
mkdir -p /opt/microprice && cd /opt/microprice
aws s3 cp "s3://${bucket}/release/microprice.tar.gz" - | tar -xz
aws s3 sync "s3://${bucket}/results" results
aws s3 sync "s3://${bucket}/data" data
docker compose -f infra/docker-compose.yml up -d --build
