# Python scripts

Run commands from the repository root. For the 8.0.2 lab use
[Quickstart](../docs/quickstart-802.md).

- `automated_quickstart.py` provisions and configures the lab.
- `teardown_802.py` removes the disposable host, VPC and EIP while preserving ECR and S3.
- `user_profile.py` manages local configuration files; legacy scenario package import/export is retired.
- `smoke_test.py` and `docs_quality.py` run no-apply repository checks.
- `fortigate_ai_app_proxy_touch.py`, `bedrock_direct_test.py` and
  `fortiaigate_chat_test.py` support targeted troubleshooting.
- `nvidia_package_cache.py` manages the optional NVIDIA package cache.

Use `python3 -m catalog802` and Lab Management for scenarios, and
`python3 -m functional_test catalog-baseline --help` for a catalog-driven test.
The 8.0.1 tools are preserved in `archive/8.0.1` and the `802-experimental`
restore point.
