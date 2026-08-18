from __future__ import annotations

import re
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import automated_quickstart  # noqa: E402
import local_setup  # noqa: E402


def appliance_args(**overrides: bool) -> Namespace:
    values = {
        "include_appliances": False,
        "include_fortigate": False,
        "include_fortiweb": False,
        "no_appliances": False,
        "no_fortigate": False,
        "no_fortiweb": False,
        "yolo": False,
        "skip_terraform": False,
    }
    values.update(overrides)
    return Namespace(**values)


class ApplianceDefaultTests(unittest.TestCase):
    def test_static_bedrock_user_is_opt_in_but_ec2_bedrock_access_remains_enabled(self) -> None:
        system_defaults = (
            REPO_ROOT / "terraform/aws-prep/00-system.auto.tfvars"
        ).read_text(encoding="utf-8")
        variable_definitions = (
            REPO_ROOT / "terraform/aws-prep/variables.tf"
        ).read_text(encoding="utf-8")

        self.assertRegex(system_defaults, r"(?m)^enable_bedrock_iam\s*=\s*false$")
        self.assertRegex(system_defaults, r"(?m)^enable_ec2_bedrock_iam\s*=\s*true$")
        self.assertRegex(
            variable_definitions,
            re.compile(
                r'variable "enable_bedrock_iam"\s*\{.*?default\s*=\s*false',
                re.DOTALL,
            ),
        )

    def test_both_appliances_are_desired_by_default(self) -> None:
        with mock.patch.object(
            automated_quickstart,
            "appliance_enabled_from_tfvars",
            return_value=True,
        ):
            self.assertEqual(
                automated_quickstart.requested_appliance_keys(appliance_args()),
                ["fortigate", "fortiweb"],
            )

    def test_persisted_appliance_opt_out_is_honored_but_include_overrides_it(self) -> None:
        with mock.patch.object(
            automated_quickstart,
            "appliance_enabled_from_tfvars",
            return_value=False,
        ):
            self.assertEqual(automated_quickstart.requested_appliance_keys(appliance_args()), [])
            self.assertEqual(
                automated_quickstart.requested_appliance_keys(
                    appliance_args(include_fortiweb=True)
                ),
                ["fortiweb"],
            )

    def test_explicit_opt_out_wins_over_default_intent(self) -> None:
        with mock.patch.object(
            automated_quickstart,
            "appliance_enabled_from_tfvars",
            return_value=True,
        ):
            self.assertEqual(
                automated_quickstart.requested_appliance_keys(
                    appliance_args(no_fortiweb=True)
                ),
                ["fortigate"],
            )
            self.assertEqual(
                automated_quickstart.requested_appliance_keys(
                    appliance_args(no_appliances=True)
                ),
                [],
            )

    def test_noninteractive_default_skips_missing_license_but_explicit_request_does_not(self) -> None:
        args = appliance_args(yolo=True)
        with mock.patch.object(
            automated_quickstart,
            "appliance_license_ready",
            return_value=(False, "license missing"),
        ):
            self.assertEqual(
                automated_quickstart.filter_noninteractive_default_appliances(
                    args, ["fortigate", "fortiweb"]
                ),
                [],
            )

        explicit = appliance_args(yolo=True, include_fortigate=True)
        with mock.patch.object(
            automated_quickstart,
            "appliance_license_ready",
            return_value=(False, "license missing"),
        ):
            self.assertEqual(
                automated_quickstart.filter_noninteractive_default_appliances(
                    explicit, ["fortigate"]
                ),
                ["fortigate"],
            )

    def test_local_setup_opt_out_suppresses_an_existing_inventory(self) -> None:
        args = appliance_args()
        with mock.patch.object(
            automated_quickstart,
            "get_layered_yaml_bool",
            side_effect=lambda key, default: False if key == "fortiweb_local_enabled" else True,
        ), mock.patch.object(Path, "exists", return_value=True):
            self.assertEqual(
                automated_quickstart.selected_local_appliance_keys(args),
                ["fortigate"],
            )

    def test_skip_terraform_redeploy_uses_only_existing_appliance_inventories(self) -> None:
        args = appliance_args(skip_terraform=True)

        def inventory_exists(path: Path) -> bool:
            return path.name == "fortigate.generated.ini"

        with mock.patch.object(Path, "exists", inventory_exists):
            self.assertEqual(
                automated_quickstart.filter_existing_appliances_for_skipped_terraform(
                    args,
                    ["fortigate", "fortiweb"],
                ),
                ["fortigate"],
            )

    def test_skip_terraform_rejects_explicit_missing_appliance(self) -> None:
        args = appliance_args(skip_terraform=True, include_fortiweb=True)
        with mock.patch.object(Path, "exists", return_value=False):
            with self.assertRaisesRegex(SystemExit, "explicitly requested"):
                automated_quickstart.filter_existing_appliances_for_skipped_terraform(
                    args,
                    ["fortiweb"],
                )

    def test_local_setup_prompts_default_on_and_records_explicit_opt_out(self) -> None:
        with mock.patch.object(local_setup, "prompt_yes_no", return_value=False) as prompt:
            result = local_setup.prompt_fortigate_appliance(
                inventory_defaults={},
                generated_defaults={},
                secret_defaults={},
                current_access_cidrs=[],
                lab_cidr="192.0.2.0/24",
            )
        self.assertTrue(prompt.call_args.args[1])
        self.assertFalse(result.enabled)
        self.assertEqual(result.generated_vars, {"fortigate_local_enabled": "false"})
        self.assertIn(
            "fortigate_local_enabled: false",
            local_setup.render_appliance_local_vars([result]),
        )

    def test_local_appliance_backend_ips_have_no_generated_default(self) -> None:
        with mock.patch.object(
            local_setup, "prompt_yes_no", side_effect=[True, False]
        ), mock.patch.object(
            local_setup, "prompt_ip_or_host", return_value="192.168.249.20"
        ), mock.patch.object(
            local_setup, "prompt_text", side_effect=["443", "apiadmin"]
        ), mock.patch.object(
            local_setup, "prompt_optional_ip", return_value=""
        ) as fortigate_ip_prompt, mock.patch.object(
            local_setup, "discover_controller_cidr", return_value=""
        ), mock.patch.object(local_setup, "write_text"):
            local_setup.prompt_fortigate_appliance(
                inventory_defaults={},
                generated_defaults={},
                secret_defaults={},
                current_access_cidrs=[],
                lab_cidr="192.168.248.0/24",
            )

        self.assertEqual(fortigate_ip_prompt.call_args.args[1], "")

        with mock.patch.object(
            local_setup, "prompt_yes_no", side_effect=[True, False]
        ), mock.patch.object(
            local_setup, "prompt_ip_or_host", return_value="192.168.249.30"
        ), mock.patch.object(
            local_setup,
            "prompt_text",
            side_effect=["443", "apiadmin", "prof_admin"],
        ), mock.patch.object(
            local_setup, "prompt_optional_ip", return_value=""
        ) as fortiweb_ip_prompt, mock.patch.object(
            local_setup, "discover_controller_cidr", return_value=""
        ), mock.patch.object(local_setup, "write_text"):
            local_setup.prompt_fortiweb_appliance(
                inventory_defaults={},
                generated_defaults={},
                secret_defaults={},
                current_access_cidrs=[],
                lab_cidr="192.168.248.0/24",
            )

        self.assertEqual(fortiweb_ip_prompt.call_args.args[1], "")


if __name__ == "__main__":
    unittest.main()
