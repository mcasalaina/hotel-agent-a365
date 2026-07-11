# Supporting Azure infrastructure

`main.bicep` is a subscription-scope deployment that:

- creates `rg-hotel-agent-a365`;
- creates one East US 2 Azure AI Search service and one StorageV2 account;
- creates the private `hotel-docs` blob container;
- grants the Foundry project and Search managed identities the required data-plane roles;
- grants the azd deployment principal the roles required to load and verify content; and
- creates the `hotel-search` connection in the existing Foundry project.

The existing Foundry account, project, model deployments, Application Insights resource, and unrelated East US Search service are referenced or left unchanged.

The Search and storage resources use managed identities and disable local/key authentication. Resource names are generic and receive a deterministic uniqueness suffix.
