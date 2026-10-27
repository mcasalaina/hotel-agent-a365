"""Create a blueprint credential and pipe it directly to the target Key Vault."""

import argparse
import json
import subprocess
from datetime import UTC, datetime


def az(*args, stdin=None):
    result = subprocess.run(
        ["az", *args, "--only-show-errors", "-o", "json"],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        # Secret-bearing commands must not echo their response bodies or arguments.
        raise RuntimeError(f"Azure operation failed: {args[0]} {args[1]}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def store(args):
    account = az("account", "show")
    if account["tenantId"] != args.tenant_id or account["id"] != args.subscription_id:
        raise RuntimeError("Azure context does not match the authorized target")
    expires = datetime.fromisoformat(args.expires_on.replace("Z", "+00:00"))
    if expires.tzinfo is None or expires <= datetime.now(UTC):
        raise RuntimeError("Credential expiry must be a future, timezone-aware timestamp")
    existing = az("keyvault", "secret", "list", "--vault-name", args.vault_name)
    if any(secret["name"] == "agent365-blueprint-client-secret" for secret in existing):
        raise RuntimeError("A blueprint secret already exists; refusing automatic rotation")
    credential = az(
        "rest",
        "--method",
        "POST",
        "--url",
        (
            "https://graph.microsoft.com/beta/applications/"
            f"{args.blueprint_id}/microsoft.graph.agentIdentityBlueprint/addPassword"
        ),
        "--body",
        json.dumps(
            {
                "passwordCredential": {
                    "displayName": "Hotel bridge runtime",
                    "endDateTime": expires.isoformat().replace("+00:00", "Z"),
                },
            }
        ),
    )
    try:
        blueprint_secret = az(
            "keyvault",
            "secret",
            "set",
            "--vault-name",
            args.vault_name,
            "--name",
            "agent365-blueprint-client-secret",
            "--expires",
            args.expires_on,
            "--file",
            "/dev/stdin",
            stdin=credential["secretText"],
        )
    except Exception:
        az(
            "rest",
            "--method",
            "POST",
            "--url",
            (
                "https://graph.microsoft.com/beta/applications/"
                f"{args.blueprint_id}/microsoft.graph.agentIdentityBlueprint/removePassword"
            ),
            "--body",
            json.dumps({"keyId": credential["keyId"]}),
        )
        raise
    finally:
        credential.pop("secretText", None)
    component = az(
        "monitor",
        "app-insights",
        "component",
        "show",
        "--app",
        args.insights_name,
        "--resource-group",
        args.resource_group,
        "--subscription",
        args.subscription_id,
    )
    insights_secret = az(
        "keyvault",
        "secret",
        "set",
        "--vault-name",
        args.vault_name,
        "--name",
        "applicationinsights-connection-string",
        "--file",
        "/dev/stdin",
        stdin=component["connectionString"],
    )
    print(
        json.dumps(
            {
                "vaultUri": f"https://{args.vault_name}.vault.azure.net/",
                "secrets": [
                    {
                        "name": name,
                        "version": secret["id"].rsplit("/", 1)[-1],
                        "expires": secret["attributes"].get("expires"),
                    }
                    for name, secret in [
                        ("agent365-blueprint-client-secret", blueprint_secret),
                        ("applicationinsights-connection-string", insights_secret),
                    ]
                ],
                "credentialKeyId": credential["keyId"],
                "credentialExpires": credential["endDateTime"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--blueprint-id", required=True)
    parser.add_argument("--vault-name", required=True)
    parser.add_argument("--insights-name", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--expires-on", required=True)
    store(parser.parse_args())
