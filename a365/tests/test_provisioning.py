import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from a365 import provision_permissions, store_runtime_secrets


class PermissionProvisioningTests(unittest.TestCase):
    def test_instance_instructions_preserve_template_and_alias(self):
        instructions = Path("manifest/README.md").read_text()
        manifest = json.loads(Path("manifest/manifest.json").read_text())
        self.assertIn("Display name: `Lyrenza Hotel Guest Services`", instructions)
        self.assertIn("Alias: `hotelguestservices`", instructions)
        self.assertEqual(manifest["name"]["short"], "Hotel Guest Services")
        self.assertEqual(manifest["id"], "c8798b5b-a68f-4815-8fcc-ca1810efc529")

    def _blueprint_requests(self, existing):
        blueprint = {
            "id": "hotel-blueprint",
            "appId": "hotel-blueprint",
            "displayName": "Hotel Blueprint",
            "signInAudience": "AzureADMyOrg",
        }
        args = argparse.Namespace(
            tenant_id="target",
            operator_id="operator",
            display_name="Hotel Blueprint",
        )
        responses = [
            [{"roleDefinitionId": "developer"}, {"roleDefinitionId": "administrator"}],
            [{"id": "developer"}],
            [{"id": "administrator"}],
            [blueprint] if existing else [],
            [{"id": "operator"}],
            RuntimeError("Stop before principal lookup"),
        ]
        with (
            patch.object(provision_permissions, "az", return_value={"tenantId": "target"}),
            patch.object(provision_permissions, "collection", side_effect=responses),
            patch.object(provision_permissions, "graph", return_value=blueprint) as graph,
            self.assertRaisesRegex(RuntimeError, "Stop before principal lookup"),
        ):
            provision_permissions.provision(args)
        return blueprint, graph

    def test_existing_blueprint_preserves_tenant_only_audience(self):
        blueprint, graph = self._blueprint_requests(existing=True)
        self.assertEqual(blueprint["signInAudience"], "AzureADMyOrg")
        for call in graph.call_args_list:
            self.assertNotIn("signInAudience", call.args[2])

    def test_new_blueprint_uses_default_tenant_only_audience(self):
        blueprint, graph = self._blueprint_requests(existing=False)
        create = graph.call_args_list[0]
        self.assertEqual(
            create.args[:2],
            (
                "POST",
                "applications/microsoft.graph.agentIdentityBlueprint",
            ),
        )
        self.assertNotIn("signInAudience", create.args[2])
        self.assertEqual(blueprint["signInAudience"], "AzureADMyOrg")
        for call in graph.call_args_list:
            self.assertNotIn("signInAudience", call.args[2])

    def test_matrix_has_exact_ten_audiences_and_graph_scopes(self):
        matrix = json.loads(Path("a365/permission-matrix.example.json").read_text())[
            "resolvedPermissions"
        ]
        self.assertEqual(len(matrix), 10)
        self.assertEqual(len({entry["resourceAppId"] for entry in matrix}), 10)
        (graph,) = [
            entry
            for entry in matrix
            if entry["resourceAppId"] == "00000003-0000-0000-c000-000000000000"
        ]
        self.assertEqual(len(graph["delegatedScopes"]), 29)
        self.assertIn("Files.ReadWrite.All", graph["delegatedScopes"])
        self.assertIn("ChannelMessage.Send", graph["delegatedScopes"])

    def test_cli_example_matches_target_without_reusing_an_instance(self):
        config = json.loads(Path("agent/a365.config.example.json").read_text())
        bindings = dict(
            line.split("=", 1)
            for line in Path("config/azd.env.example").read_text().splitlines()
            if line and not line.startswith("#")
        )
        self.assertEqual(config["tenantId"], bindings["AGENT365_TENANT_ID"])
        self.assertEqual(config["subscriptionId"], bindings["AZURE_SUBSCRIPTION_ID"])
        self.assertEqual(config["clientAppId"], bindings["AGENT365_BLUEPRINT_CLIENT_ID"])
        self.assertEqual(config["agentUserObjectId"], "")
        self.assertEqual(config["agentIdentityClientId"], "")
        self.assertNotIn("2612", json.dumps(config))

    @patch.object(provision_permissions, "az")
    def test_delegated_grants_use_stable_api(self, az):
        provision_permissions.graph("POST", "oauth2PermissionGrants", {"scope": "User.Read"})
        self.assertIn(
            "https://graph.microsoft.com/v1.0/oauth2PermissionGrants",
            az.call_args.args,
        )

    @patch.object(provision_permissions, "az")
    def test_blueprint_inheritance_uses_agent_api(self, az):
        provision_permissions.graph("GET", "applications/hotel/inheritablePermissions")
        self.assertIn(
            "https://graph.microsoft.com/beta/applications/hotel/inheritablePermissions",
            az.call_args.args,
        )

    @patch.object(provision_permissions, "az", return_value={"tenantId": "other"})
    def test_wrong_tenant_fails_before_writes(self, az):
        with self.assertRaisesRegex(RuntimeError, "requested tenant"):
            provision_permissions.provision(argparse.Namespace(tenant_id="target"))
        az.assert_called_once_with("account", "show")


class SecretStorageTests(unittest.TestCase):
    def setUp(self):
        self.args = argparse.Namespace(
            tenant_id="target",
            subscription_id="subscription",
            blueprint_id="blueprint",
            vault_name="vault",
            insights_name="insights",
            resource_group="hotel",
            expires_on="2027-10-27T00:00:00Z",
        )

    @patch.object(store_runtime_secrets, "az")
    def test_secret_values_are_only_passed_through_stdin(self, az):
        az.side_effect = [
            {"tenantId": "target", "id": "subscription"},
            [],
            {"secretText": "sensitive-blueprint", "keyId": "key", "endDateTime": "future"},
            {
                "id": "https://vault/secrets/blueprint/version-one",
                "attributes": {"expires": "2027-10-27"},
            },
            {"connectionString": "sensitive-telemetry"},
            {"id": "https://vault/secrets/insights/version-two", "attributes": {"expires": None}},
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            store_runtime_secrets.store(self.args)
        calls = az.call_args_list
        self.assertEqual(calls[3].kwargs["stdin"], "sensitive-blueprint")
        self.assertEqual(calls[5].kwargs["stdin"], "sensitive-telemetry")
        for call in calls:
            self.assertNotIn("sensitive-blueprint", str(call.args))
            self.assertNotIn("sensitive-telemetry", str(call.args))
        self.assertNotIn("sensitive-", output.getvalue())
        password_body = json.loads(calls[2].args[-1])
        self.assertEqual(
            password_body["passwordCredential"]["endDateTime"],
            "2027-10-27T00:00:00Z",
        )

    @patch.object(store_runtime_secrets, "az")
    def test_vault_failure_revokes_new_credential(self, az):
        az.side_effect = [
            {"tenantId": "target", "id": "subscription"},
            [],
            {"secretText": "sensitive-blueprint", "keyId": "key", "endDateTime": "future"},
            RuntimeError("vault unavailable"),
            None,
        ]
        with self.assertRaisesRegex(RuntimeError, "vault unavailable"):
            store_runtime_secrets.store(self.args)
        revoke = az.call_args_list[4]
        self.assertTrue(revoke.args[4].endswith("/removePassword"))
        self.assertEqual(json.loads(revoke.args[-1]), {"keyId": "key"})

    @patch.object(store_runtime_secrets, "az")
    def test_existing_secret_is_not_rotated(self, az):
        az.side_effect = [
            {"tenantId": "target", "id": "subscription"},
            [{"name": "agent365-blueprint-client-secret"}],
        ]
        with self.assertRaisesRegex(RuntimeError, "refusing automatic rotation"):
            store_runtime_secrets.store(self.args)
        self.assertEqual(az.call_count, 2)

    @patch.object(store_runtime_secrets, "az")
    def test_wrong_subscription_fails_before_secret_reads(self, az):
        az.return_value = {"tenantId": "target", "id": "other"}
        with self.assertRaisesRegex(RuntimeError, "authorized target"):
            store_runtime_secrets.store(self.args)
        az.assert_called_once_with("account", "show")


if __name__ == "__main__":
    unittest.main()
