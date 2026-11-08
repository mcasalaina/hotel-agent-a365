# Agent 365 host parity

This directory reserves the Agent 365 host, authentication, notification, OBO, and diagnostics surface. The bootstrap contains only safe examples. Live IDs, generated CLI configuration, tokens, and tenant-specific values must remain outside source control.

Deploy the bridge with `infra/agent365-bridge.bicep` as an Azure Container App.
Supply the target environment, attached user-assigned identity, immutable image,
Foundry endpoint and Key Vault secret URIs explicitly. The template creates no
registry, vault, identity or RBAC assignment. Provision and verify those scoped
dependencies before deployment.

The stable Agent 365 SDK pins include notification routing compatibility.
Known `productInfo` entity casing is normalized without replacing the original
request's headers or claims. Email notifications use isolated hosted turns and
exact message references; the bridge alone delivers the reply. A missing
agent-user authorization exchange fails closed rather than silently invoking
Foundry as the bridge's managed identity.

Run the targeted regression checks with
`python -m pytest tests/unit/test_bridge_readiness.py`.
