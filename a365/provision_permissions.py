"""Provision a Hotel blueprint and verify tenant-local permission parity using az."""

import argparse
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

GRAPH = "https://graph.microsoft.com/beta"
A365_MANAGER_APP_ID = "e8be65d6-d430-4289-a665-51bf2a194bda"


def az(*args):
    result = subprocess.run(
        ["az", *args, "--only-show-errors", "-o", "json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def graph(method, path, body=None):
    base = (
        "https://graph.microsoft.com/v1.0" if path.startswith("oauth2PermissionGrants") else GRAPH
    )
    args = ["rest", "--method", method, "--url", f"{base}/{path}"]
    if body is not None:
        args += ["--body", json.dumps(body)]
    return az(*args)


def collection(path, **query):
    suffix = "?" + urlencode(query) if query else ""
    response = graph("GET", path + suffix)
    if response.get("@odata.nextLink"):
        raise RuntimeError("Unexpected pagination in narrowly scoped Hotel query")
    return response["value"]


def provision(args):
    account = az("account", "show")
    if account["tenantId"] != args.tenant_id:
        raise RuntimeError("Azure CLI is not authenticated to the requested tenant")
    assignments = collection(
        "roleManagement/directory/roleAssignments",
        **{"$filter": f"principalId eq '{args.operator_id}'"},
    )
    assigned = {item["roleDefinitionId"] for item in assignments}
    for role in ["Agent ID Developer", "Agent ID Administrator"]:
        (definition,) = collection(
            "roleManagement/directory/roleDefinitions",
            **{"$filter": f"displayName eq '{role}'"},
        )
        if definition["id"] not in assigned:
            graph(
                "POST",
                "roleManagement/directory/roleAssignments",
                {
                    "principalId": args.operator_id,
                    "roleDefinitionId": definition["id"],
                    "directoryScopeId": "/",
                },
            )

    blueprints = collection(
        "applications/microsoft.graph.agentIdentityBlueprint",
        **{"$filter": f"displayName eq '{args.display_name}'"},
    )
    if len(blueprints) > 1:
        raise RuntimeError("Multiple Hotel blueprints match the business name")
    blueprint = (
        blueprints[0]
        if blueprints
        else graph(
            "POST",
            "applications/microsoft.graph.agentIdentityBlueprint",
            {
                "displayName": args.display_name,
                "sponsors@odata.bind": [f"{GRAPH}/users/{args.operator_id}"],
                "owners@odata.bind": [f"{GRAPH}/users/{args.operator_id}"],
                "managerApplications": [A365_MANAGER_APP_ID],
            },
        )
    )
    blueprint_path = f"applications/{blueprint['id']}/microsoft.graph.agentIdentityBlueprint"
    graph(
        "PATCH",
        blueprint_path,
        {
            "managerApplications": [A365_MANAGER_APP_ID],
        },
    )
    owners = collection(f"applications/{blueprint['id']}/owners")
    if not any(owner["id"] == args.operator_id for owner in owners):
        graph(
            "POST",
            f"applications/{blueprint['id']}/owners/$ref",
            {
                "@odata.id": f"{GRAPH}/directoryObjects/{args.operator_id}",
            },
        )
    principals = collection(
        "servicePrincipals",
        **{"$filter": f"appId eq '{blueprint['appId']}'"},
    )
    principal = (
        principals[0]
        if principals
        else graph(
            "POST",
            "servicePrincipals/microsoft.graph.agentIdentityBlueprintPrincipal",
            {"appId": blueprint["appId"]},
        )
    )
    result = {
        "tenantId": args.tenant_id,
        "blueprint": {
            "displayName": blueprint["displayName"],
            "appId": blueprint["appId"],
            "objectId": blueprint["id"],
            "servicePrincipalId": principal["id"],
        },
        "permissions": [],
        "permissionParityVerified": False,
    }

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")

    save()
    print(json.dumps(result["blueprint"]), flush=True)
    inheritance_path = (
        f"applications/{blueprint['id']}/"
        "microsoft.graph.agentIdentityBlueprint/inheritablePermissions"
    )
    inheritable = collection(inheritance_path)
    grants = collection(
        "oauth2PermissionGrants",
        **{"$filter": f"clientId eq '{principal['id']}'"},
    )
    role_assignments = collection(f"servicePrincipals/{principal['id']}/appRoleAssignments")
    required_access = []
    matrix = json.loads(args.matrix.read_text())["resolvedPermissions"]
    for entry in matrix:
        resource_id = entry["resourceAppId"]
        resources = collection(
            "servicePrincipals",
            **{"$filter": f"appId eq '{resource_id}'"},
        )
        resource = (
            resources[0]
            if resources
            else graph(
                "POST",
                "servicePrincipals",
                {"appId": resource_id},
            )
        )
        scopes = {
            s["value"]: s
            for s in resource.get(
                "oauth2PermissionScopes", resource.get("publishedPermissionScopes", [])
            )
            if s["isEnabled"]
        }
        roles = {r["value"]: r for r in resource["appRoles"] if r["isEnabled"]}
        missing = set(entry["delegatedScopes"]) - scopes.keys()
        missing_roles = set(entry.get("applicationRoles", [])) - roles.keys()
        if missing or missing_roles:
            raise RuntimeError(
                f"{entry['resource']}: unavailable scopes {missing}, roles {missing_roles}"
            )
        grant_body = {
            "clientId": principal["id"],
            "consentType": "AllPrincipals",
            "resourceId": resource["id"],
            "scope": " ".join(entry["delegatedScopes"]),
        }
        existing = [
            g
            for g in grants
            if g["resourceId"] == resource["id"] and g["consentType"] == "AllPrincipals"
        ]
        if len(existing) > 1:
            raise RuntimeError("Duplicate tenant-wide grants require investigation")
        if existing:
            grant = existing[0]
            if set(grant["scope"].split()) != set(entry["delegatedScopes"]):
                graph(
                    "PATCH",
                    f"oauth2PermissionGrants/{grant['id']}",
                    {
                        "scope": grant_body["scope"],
                    },
                )
        else:
            grant = graph("POST", "oauth2PermissionGrants", grant_body)
        inheritance_body = {
            "resourceAppId": resource_id,
            "inheritableScopes": {
                "@odata.type": "microsoft.graph.allAllowedScopes",
                "kind": "allAllowed",
            },
            "inheritableRoles": {
                "@odata.type": "microsoft.graph.allAllowedRoles",
                "kind": "allAllowed",
            },
        }
        if any(i["resourceAppId"] == resource_id for i in inheritable):
            graph("PATCH", f"{inheritance_path}/{resource_id}", inheritance_body)
        else:
            graph("POST", inheritance_path, inheritance_body)
        app_role_ids = []
        for role_name in entry.get("applicationRoles", []):
            role_id = roles[role_name]["id"]
            app_role_ids.append(role_id)
            if not any(
                r["resourceId"] == resource["id"] and r["appRoleId"] == role_id
                for r in role_assignments
            ):
                graph(
                    "POST",
                    f"servicePrincipals/{principal['id']}/appRoleAssignments",
                    {
                        "principalId": principal["id"],
                        "resourceId": resource["id"],
                        "appRoleId": role_id,
                    },
                )
        scope_ids = {name: scopes[name]["id"] for name in entry["delegatedScopes"]}
        required_access.append(
            {
                "resourceAppId": resource_id,
                "resourceAccess": [
                    {"id": scope_id, "type": "Scope"} for scope_id in scope_ids.values()
                ]
                + [{"id": role_id, "type": "Role"} for role_id in app_role_ids],
            }
        )
        result["permissions"].append(
            {
                **entry,
                "resourceServicePrincipalId": resource["id"],
                "grantId": grant["id"],
                "scopeIds": scope_ids,
                "applicationRoleIds": app_role_ids,
            }
        )
        save()
        print(f"Configured {entry['resource']}", flush=True)
    graph(
        "PATCH",
        f"applications/{blueprint['id']}/microsoft.graph.agentIdentityBlueprint",
        {"requiredResourceAccess": required_access},
    )
    verified_grants = collection(
        "oauth2PermissionGrants",
        **{"$filter": f"clientId eq '{principal['id']}'"},
    )
    verified_inheritance = collection(inheritance_path)
    assert len(verified_grants) == len(matrix) == len(verified_inheritance) == 10
    for entry in result["permissions"]:
        (grant,) = [
            g for g in verified_grants if g["resourceId"] == entry["resourceServicePrincipalId"]
        ]
        assert grant["consentType"] == "AllPrincipals"
        assert set(grant["scope"].split()) == set(entry["delegatedScopes"])
        (inherited,) = [
            i for i in verified_inheritance if i["resourceAppId"] == entry["resourceAppId"]
        ]
        assert inherited["inheritableScopes"]["kind"] == "allAllowed"
        assert inherited["inheritableRoles"]["kind"] == "allAllowed"
    result["inheritablePermissions"] = verified_inheritance
    result["permissionParityVerified"] = True
    save()
    print("Verified TEN grants and TEN inheritable entries", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--display-name", default="hotel-agent-bridge Blueprint")
    parser.add_argument("--matrix", type=Path, default=Path("a365/permission-matrix.example.json"))
    parser.add_argument("--output", type=Path, required=True)
    provision(parser.parse_args())
