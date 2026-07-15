# Hotel Guest Services Agent 365 template

This folder packages the Agent 365 **agent template** for the independently owned
`hotel-agent-bridge Blueprint`. Uploading this package registers a reusable template whose
instances receive their own Agent 365 identity and agent user. The blueprint routes activity
requests to the Container Apps bridge, which delegates intelligence to the
`hotel-servicing-agent` Foundry Hosted Agent.

## Live IDs

- Blueprint client ID: `f1ae4991-0418-470b-96d5-7f7df43ab5d2`
- Agentic user template ID: `9a2da06d-059c-4b40-910f-ca8e0a6b1730`

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

1. Reject the earlier non-template tenant publication if it remains pending.
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
     `f1ae4991-0418-470b-96d5-7f7df43ab5d2`.
   - Status is **Available**. If it is **Not activated**, select **Activate**, choose
     **All users**, apply the default agent-template policy, and finish the separate activation
     wizard. The upload wizard can retain the requested activation audience without completing
     this registry activation.

The live template was published and activated through this path on 2026-07-14.

## Configure the owned blueprint

The template is not messageable until its blueprint has an API notification endpoint.

1. Ensure the operator is an owner of the blueprint app registration and has the
   **Agent ID Developer** and **Agent ID Administrator** directory roles. Global Administrator by
   itself does not make the blueprint editable.
2. Open:
   `https://dev.teams.microsoft.com/tools/agent-blueprint/f1ae4991-0418-470b-96d5-7f7df43ab5d2/configuration`
3. Set **Agent Type** to **API Based**.
4. Read the deployed Container Apps FQDN rather than copying an endpoint from another project:

   ```bash
   az containerapp show \
     --resource-group rg-aycabas-3iqs \
     --name hotel-agent-bridge-a365 \
     --query properties.configuration.ingress.fqdn \
     --output tsv
   ```

5. Set **Notification URL** to that exact value and save. The live value is:
   `https://hotel-agent-bridge-a365.gentleforest-8d33b38e.westus.azurecontainerapps.io/api/messages`

## Create an instance

1. Return to **Agents > All agents > Registry**, open **Hotel Guest Services**, and select
   **Add instance**.
2. Supply a generic display name and alias, select a human owner/reports-to user, and create the
   instance. Agent 365 assigns the selected agent-template license automatically.
3. The live demo instance is:
   - Display name: `Hotel Guest Services`
   - UPN: `hotelguestservices@cam3652609.onmicrosoft.com`
   - Agent-user object ID: `ba923ab8-d1d8-46de-98a4-229cf0b29e6b`
   - Entra agent ID: `cc4f4078-c463-494a-a5fc-0b63a6995296`
4. An administrator-created instance is provisioned directly. If a nonadministrator creates an
   instance request from the Agent Store instead, approve it under **Agents > All agents >
   Requests**.

## Grant runtime access

Teams invokes the Hosted Agent as the agentic user, not as the administrator who created it.
Grant the instance user access to both Foundry scopes and the Fabric workspace:

```bash
AGENTIC=ba923ab8-d1d8-46de-98a4-229cf0b29e6b
ACCT="/subscriptions/27b0139a-16b4-42bf-9ec9-c6db3768245e/resourceGroups/rg-aycabas-3iqs/providers/Microsoft.CognitiveServices/accounts/4iq-foundry-project-resource"
PROJ="$ACCT/projects/4iq-foundry-project"

az role assignment create --role "Azure AI Developer" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$ACCT"
az role assignment create --role "Azure AI Developer" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$PROJ"
az role assignment create --role "Cognitive Services User" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$ACCT"
az role assignment create --role "Cognitive Services OpenAI User" \
  --assignee-object-id "$AGENTIC" --assignee-principal-type User --scope "$ACCT"
```

Add the same user as **Contributor** to Fabric workspace
`660ed238-54b7-42bd-8b1b-cf2ee47a11ba` with
`POST /v1/workspaces/{workspaceId}/roleAssignments`:

```json
{
  "principal": {
    "id": "ba923ab8-d1d8-46de-98a4-229cf0b29e6b",
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
2. Select `Hotel Guest Services` (`hotelguestservices@cam3652609.onmicrosoft.com`).
3. Open **Delegation**.
4. Under **Read and manage (Full Access)**, select **Edit > Add members**.
5. Select the required operators, select **Save**, and confirm the change.
6. Verify the Full Access count. Check immediately and retry for no more than one minute before
   investigating another cause. Outlook automapping may still take longer before the mailbox appears
   in the operator's client.

The demo mailbox grants Full Access to:

- `mcasalaina.local@cam3652609.onmicrosoft.com`
- `aycabas.local@cam3652609.onmicrosoft.com`

Do not grant Send As or Send on behalf unless the demo explicitly requires a human operator to send
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
POST /v1.0/applications/f1ae4991-0418-470b-96d5-7f7df43ab5d2/
  microsoft.graph.agentIdentityBlueprint/inheritablePermissions
```

```json
{
  "resourceAppId": "<resource application ID>",
  "inheritableScopes": {
    "@odata.type": "microsoft.graph.enumeratedScopes",
    "scopes": ["user_impersonation"]
  }
}
```

Verify with:

```http
GET /v1.0/applications/microsoft.graph.agentIdentityBlueprint/
  f1ae4991-0418-470b-96d5-7f7df43ab5d2/inheritablePermissions
```

Do not stop after adding the Foundry OBO resources. Every permission the blueprint expects to
inherit must have both a tenant-wide `oauth2PermissionGrant` on the blueprint service principal and
a matching `inheritablePermissions` entry. The live blueprint was initially missing consent grants
for three resources even though their scopes were already inheritable:

| Resource | Application ID | Tenant service-principal ID | Granted scopes |
| --- | --- | --- | --- |
| Microsoft Graph | `00000003-0000-0000-c000-000000000000` | `78bfd122-6a12-493a-99df-5af2bfe6ac55` | `Chat.ReadWrite Mail.ReadWrite Mail.Send User.Read.All` |
| Power Platform API | `8578e004-a5c6-46e7-913e-12f58912df43` | `2947ae2a-9150-4362-8bf7-f98f15175817` | `Connectivity.Connections.Read` |
| Agent Tools | `ea9ffc3e-8a23-4a7d-836d-234d7c7565c1` | `c3a8ee6e-876c-4131-b788-7b116ff933df` | `McpServers.Mail.All McpServers.Teams.All McpServersMetadata.Read.All` |

The service-principal IDs are tenant-local and must be resolved by application ID in every tenant.
The scopes above were added on 2026-07-14, bringing the blueprint to nine tenant-wide grants:
Messaging Bot, Microsoft Cognitive Services, Azure Machine Learning Services, three Work IQ V2
resources, Microsoft Graph, Power Platform API, and Agent Tools.

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

The demo tenant was verified on 2026-07-14 with all five mutation controls already enabled. This
tenant setting permits Work IQ writes but does not force this agent to perform them: the current
Hosted Agent intentionally retains positive read-only tool allowlists and refuses Microsoft 365
mutations.
