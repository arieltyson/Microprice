# Security Policy

## Supported Versions

Security fixes are applied to the `main` branch only.

## Reporting a Vulnerability

Please report vulnerabilities through GitHub private vulnerability reporting on this repository (Security tab, "Report a vulnerability"). Do not open a public issue for a security problem.

Include the affected file and commit, the steps to reproduce, and the impact you expect. You will get an acknowledgement within seven days.

## Scope

- Credentials or license files committed to the repository
- Third-party data committed in breach of its terms
- Vulnerabilities in the WebSocket gateway, the multicast feed handler or the dashboard
- Over-broad cloud permissions in `infra/`

## Handling of Secrets and Data

- AWS credentials come from the environment or AWS SSO and are never stored in the repository.
- The kdb+ license file lives outside the repository.
- Third-party market data is downloaded by script into `data/`, which is ignored by git.
- A gitleaks pre-commit hook blocks commits that contain secrets. Run `make hooks` once per clone to enable it. The same scan runs in the CI workflow on manual trigger.
