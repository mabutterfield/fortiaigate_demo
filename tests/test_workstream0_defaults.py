from __future__ import annotations

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
    def test_both_appliances_are_desired_by_default(self) -> None:
        self.assertEqual(
            automated_quickstart.requested_appliance_keys(appliance_args()),
            ["fortigate", "fortiweb"],
        )

    def test_explicit_opt_out_wins_over_default_intent(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
