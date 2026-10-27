# Agent 365 publication

This directory holds source-controlled permission and publication inputs that are separate from the runtime host in `agent/` and the four-file package in `manifest/`.

Generated tenant configuration, consent results, tokens, and publication packages are not committed.

The published template remains `Hotel Guest Services`. Its instance display name must be exactly
`Lyrenza Hotel Guest Services`, with alias `hotelguestservices`. Keep the existing blueprint,
template identifiers, technical resource names, and mailbox alias. If an instance already exists,
update its display name through the supported management path rather than creating a duplicate.

The reproducible permission contract is in `permission-matrix.example.json`. Resolve every resource
application ID to a service-principal object ID in the target tenant before creating the
`oauth2PermissionGrant`; never reuse service-principal IDs from another tenant.

The checked-in matrix is the complete permission baseline: 29 Microsoft Graph delegated scopes
and nine other resource audiences. All ten resources use `allAllowed` inheritable scopes and
roles; only observability has an application role to inherit. No source-tenant discovery is
necessary.

`provision_permissions.py` uses the existing Azure CLI authentication, checks the tenant, resolves
each resource by application ID, and creates or reconciles the blueprint's grants and inheritance.
It preserves the blueprint's existing sign-in audience and leaves newly created blueprints at
the Graph API's tenant-only `AzureADMyOrg` default. Multitenant distribution is not required for
same-tenant publication.

The helper also assigns the operator's Agent ID directory roles, adds blueprint
ownership, and associates Microsoft 365 AppCatalogServices through
`managerApplications`. Run it only with approval for all included authority
changes. Its output contains identifiers and permission names only, and it never
creates an instance. A separate catalog-manager directory-role grant is not
implemented by this helper.

The target template is already published and Available without a catalog-manager assignment.
Do not perform that optional manager grant as part of this deployment.

`store_runtime_secrets.py` creates the blueprint credential and streams it directly to Key Vault
through standard input, without putting the value in command arguments, local files, or output.
It refuses to rotate an existing credential automatically. Run this only in an authorized execution
context that permits credential creation. The bridge reads both runtime secrets through managed
identity Key Vault references.
