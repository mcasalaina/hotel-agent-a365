# Hotel Guest Services Agent 365 template

This folder packages the Agent 365 **agent template** for the independently owned
`hotel-agent-bridge Blueprint`. Uploading this package registers a reusable template whose
instances receive their own Agent 365 identity and agent user. The blueprint routes activity
requests to the Container Apps bridge, which delegates intelligence to the
`hotel-servicing-agent` Foundry Hosted Agent.

## Target tenant and identifiers

- Tenant: `cam3652701`, ID `e1cffe86-c44d-4b35-8157-2d32636babb5`
- Subscription: `8e2d733e-27bd-4df5-8be5-d6a540529106`
- Blueprint client/object ID: `c8798b5b-a68f-4815-8fcc-ca1810efc529`
- Blueprint service-principal object ID: `0b5675aa-4715-4f4c-9bf2-d63de9c5d3d7`
- Agentic user template ID: `147192a5-2b44-49c7-bff7-5859c442a1c8`
- Bridge resource group: `rg-hotel-agent-a365-2701`
- Bridge managed identity: `id-hotel-agent-bridge-2701`
- Verified bridge messaging URL:
  `https://hotel-agent-bridge-a365.nicewater-f4997702.eastus2.azurecontainerapps.io/api/messages`
- Managed-identity client ID: `e16d8ba8-7d75-4f02-8691-943888f90c10`
- Managed-identity principal ID: `77fe3659-b730-4b89-9677-c8fa7f1c3d90`
- Key Vault URI: `https://kv-hotel-a365-2701.vault.azure.net/`
- Runtime secret names: `agent365-blueprint-client-secret`,
  `applicationinsights-connection-string`

The instance identity and agent-user object IDs are assigned by the registry's **Add instance**
workflow. Record its actual returned IDs; do not reuse IDs from another tenant.
Keep the blueprint's `AzureADMyOrg` audience. A catalog-manager directory-role
assignment to Microsoft 365 AppCatalogServices
(`e8be65d6-d430-4289-a665-51bf2a194bda`) grants authority to create agent
identities and agent users. That separate role grant was not needed for this
tenant's Available template. Do not add it or broaden the sign-in audience as
part of replaying the source.

The required linkage is:

- `manifest.json.id` equals
  `agenticUserTemplateManifest.json.agentIdentityBlueprintId`.
- `manifest.json.agenticUserTemplates[0].id` equals
  `agenticUserTemplateManifest.json.id`.

## Build

The package must contain exactly four files at its root:

```bash
cd manifest
rm -f manifest.zip
zip -X -j manifest.zip manifest.json agenticUserTemplateManifest.json color.png outline.png
```

`manifest.zip` is a generated artifact and must not be committed.

## Upload

Do not use **Settings > Integrated apps > Upload custom apps**. That surface uploads an ordinary
Teams/Microsoft 365 app and does not create the required Agent 365 template.

1. Reuse an existing signed-in built-in browser tab. Do not create or close browser tabs.
2. In Microsoft 365 admin center, go to **Agents > All agents > Registry**.
3. In the command bar, select **Add agent**. At narrower window widths this action is hidden under
   the **...** (**More actions**) button to the right of **Refresh** and **Export**.
4. In the **Upload agent** wizard, choose `manifest.zip`. Successful validation advances directly
   to **Publish to users** and identifies the agent as **Hotel Guest Services**.
5. Publish to **All users**, activate for **All users**, apply
   **Default policy template for agent templates**, review permissions, and publish.
6. Open the new registry item and verify all of the following before proceeding:
   - Type is **Agent template**.
   - Entra agent ID is the blueprint client ID
     `c8798b5b-a68f-4815-8fcc-ca1810efc529`.
   - Status is **Available**. If it is **Not activated**, select **Activate**, choose
     **All users**, apply the default agent-template policy, and finish the separate activation
     wizard. The upload wizard can retain the requested activation audience without completing
     this registry activation.

Package version `1.0.1` contains the target blueprint and template identifiers. Publication and
activation must be verified in the target registry; package generation alone is not publication.

## Configure the owned blueprint

The template is not messageable until its blueprint has an API notification endpoint.

1. Ensure the operator is an owner of the blueprint app registration and has the
   **Agent ID Developer** and **Agent ID Administrator** directory roles. Global Administrator by
   itself does not make the blueprint editable.
2. Open:
   `https://dev.teams.microsoft.com/tools/agent-blueprint/c8798b5b-a68f-4815-8fcc-ca1810efc529/configuration`
3. Set **Agent Type** to **API Based**.
4. Read the deployed Container Apps FQDN rather than copying an endpoint from another project:

   ```bash
   az containerapp show \
     --resource-group rg-hotel-agent-a365-2701 \
     --name hotel-agent-bridge-a365 \
     --subscription 8e2d733e-27bd-4df5-8be5-d6a540529106 \
     --query properties.configuration.ingress.fqdn \
     --output tsv
   ```

5. Append `/api/messages` to that exact HTTPS FQDN and save it as the **Notification URL**.
   Record the verified deployed URL rather than assuming an environment's hostname.

## Create an instance

1. Return to **Agents > All agents > Registry**, open **Hotel Guest Services**, and select
   **Add instance**.
2. Supply the exact instance display name and alias below, select a human owner/reports-to user, and create the
   instance. Agent 365 assigns the selected agent-template license automatically.
3. Create the tenant-local instance as:
   - Display name: `Lyrenza Hotel Guest Services`
   - Alias: `hotelguestservices`
   - Manager: `mcasalaina@cam3652701.onmicrosoft.com`
   - Expected UPN: `hotelguestservices@cam3652701.onmicrosoft.com`
   - Agent-user object ID and Entra agent ID: record the newly created instance's actual IDs.
   The reusable template remains `Hotel Guest Services`. Do not rename the blueprint, create
   another template, or change the alias. If an instance already exists, update its display name
   through the supported management path instead of creating a duplicate.
4. An administrator-created instance is provisioned directly. If a nonadministrator creates an
   instance request from the Agent Store instead, approve it under **Agents > All agents >
   Requests**.

## Grant runtime access

Teams invokes the Hosted Agent as the agentic user, not as the administrator who created it.
Grant the instance user access to both Foundry scopes and the Fabric workspace:

```bash
AGENTIC=<agent-user-object-id>
ACCT="/subscriptions/8e2d733e-27bd-4df5-8be5-d6a540529106/resourceGroups/rg-mcasalaina-4iqs-2701/providers/Microsoft.CognitiveServices/accounts/mcasalaina-4iqs-2701-resource"
PROJ="$ACCT/projects/mcasalaina-4iqs-2701"

az role assignment create --role "Azure AI Developer" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$ACCT"
az role assignment create --role "Azure AI Developer" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$PROJ"
az role assignment create --role "Cognitive Services User" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$ACCT"
```

Do not add Cognitive Services OpenAI User unless an observed runtime authorization failure
demonstrates that the existing scoped roles are insufficient.

Add the same user as **Contributor** to Fabric workspace
`f4aa1304-d45e-4bbc-8c17-9890b1f6c2a7` with
`POST /v1/workspaces/{workspaceId}/roleAssignments`:

```json
{
  "principal": {
    "id": "<agent-user-object-id>",
    "type": "User"
  },
  "role": "Contributor"
}
```

Verify both assignments before testing. In this tenant, check changes immediately and retry for no
more than one minute before investigating another cause. The authoritative acceptance test is a real
Teams DM from the instance's manager; Bot Service Web Chat and Direct Line do not supply the Agent
365 user context required by Work IQ.

## Delegate the agent mailbox to human operators

This is a human-observability step, not a Hosted Agent runtime permission. Full Access lets the
selected operators open the agent's mailbox, but it does not grant Send As or Send on behalf.

1. In Exchange admin center, go to **Recipients > Mailboxes**.
2. Select `Lyrenza Hotel Guest Services` (`hotelguestservices@cam3652701.onmicrosoft.com`).
3. Open **Delegation**.
4. Under **Read and manage (Full Access)**, select **Edit > Add members**.
5. Select the required operators, select **Save**, and confirm the change.
6. Verify the Full Access count. Check immediately and retry for no more than one minute before
   investigating another cause. Outlook automapping may still take longer before the mailbox appears
   in the operator's client.

Grant Full Access to:

- `mcasalaina@cam3652701.onmicrosoft.com`

Do not grant Send As or Send on behalf unless the scenario explicitly requires a human operator to send
as the agent.

The blueprint also needs tenant-wide admin-consent grants and matching inheritable permissions for
both Foundry OBO resources:

- Microsoft Cognitive Services app ID `7d312290-28c8-473c-a0ed-8e53749b6d6d`:
  `user_impersonation`
- Azure Machine Learning Services app ID `18a66f5f-dbdf-4c17-9dd7-1634712a9cbe`:
  `user_impersonation`

Resolve each tenant-local service-principal object ID by app ID before creating its
`oauth2PermissionGrant`; do not copy service-principal object IDs from another tenant. Add the
matching inheritable permission with:

```http
POST /beta/applications/c8798b5b-a68f-4815-8fcc-ca1810efc529/
  microsoft.graph.agentIdentityBlueprint/inheritablePermissions
```

```json
{
  "resourceAppId": "<resource application ID>",
  "inheritableScopes": {
    "@odata.type": "microsoft.graph.allAllowedScopes",
    "kind": "allAllowed"
  },
  "inheritableRoles": {
    "@odata.type": "microsoft.graph.allAllowedRoles",
    "kind": "allAllowed"
  }
}
```

Verify with:

```http
GET /beta/applications/c8798b5b-a68f-4815-8fcc-ca1810efc529/
  microsoft.graph.agentIdentityBlueprint/inheritablePermissions
```

Do not stop after adding the Foundry OBO resources. Every permission the blueprint expects to
inherit must have both a tenant-wide `oauth2PermissionGrant` on the blueprint service principal and
a matching `inheritablePermissions` entry. The complete contract, including all 29 Graph scopes
and the nine other audiences, is `a365/permission-matrix.example.json`. Resolve resource service
principals by those application IDs in the target tenant. Verify ten tenant-wide delegated grants,
the Observability application role, and ten matching `allAllowed` scope-and-role inheritance entries.

Configure the complete grant and inheritance set **before** creating an instance. Microsoft
documents that inheritable permissions are applied to newly created agent identities; do not assume
that adding an inheritable resource retroactively repairs an existing identity. If an instance was
created first and still produces silent Teams messages with zero Foundry telemetry, create a clean
instance after finalizing the blueprint, grant that new agent user Foundry and Fabric access, and
validate it before deleting the original.

## Verify the Work IQ tenant policy

Work IQ mutation governance is independent of OAuth consent, inheritable permissions, tool
availability, and mailbox licensing. The tenant policy defaults to read-only in a new tenant.

1. In Microsoft 365 admin center, go to **Agents > Tools**.
2. Open **Work IQ MCP**. Use the generic `Work IQ MCP` item, not one of the individual preview
   server entries.
3. Open **Policies**.
4. Under **Mutations**, enable **Allow write actions** and the supported create, partial-update,
   replace, and delete actions required by the tenant.
5. Save, check immediately, and retry for no more than one minute. Restart or redeploy long-running
   agent hosts so they discard cached pre-policy tokens.

Verify the policy in this target tenant. OAuth consent alone does not establish that the tenant
permits write actions; runtime tool allowlists and hotel servicing policy still constrain usage.

## Final email acceptance

After the mailbox, bridge, Foundry Hosted Agent, and Hotel Fabric runtime are active, confirm Maria
Garcia's `RES-FAMILY-2026` reservation in Fabric and follow the acceptance gate in `DEPLOYMENT.md`.
Send only from the tenant Maria mailbox
(`maria.garcia@cam3652701.onmicrosoft.com`) to
`hotelguestservices@cam3652701.onmicrosoft.com`; never substitute the administrator's mailbox or a
spoofed From address.
