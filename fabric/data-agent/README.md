# HotelOperationsAgent

`HotelOperationsAgent` is source-controlled as a **draft** Data Agent definition under `draft/Files/Config/...`.

Deployment updates only the draft definition. Publication is intentionally separated; the normal
release workflow is `HotelDataAgentRuntimePublish`.

On October 27 the operator explicitly directed publication of the verified native draft through
the public `staging/publish` API. The three published source fingerprints match staging, and six
of seven production MCP isolation cases pass. The ontology-relationship case fails. This one-time
publication did not fabricate native readiness evidence or change the notebook's future release
gate. Native SQL Topics and model-owned Prep for AI remain unverified; publication is not full
configuration acceptance.

Prepare the sources through the supported `fabric-data-agent-sdk` before publication. Fabric must
synchronize the live SQL endpoint schemas, select the governed table sets, and persist the native
descriptions and examples. Definition-only imports can leave handcrafted lakehouse elements in a
`NotAvailable` runtime state.
The publish notebook then adopts and verifies the existing native sources without adding, removing,
or rewriting them. This preserves separately configured ontology context, Topics, and model-owned
Prep for AI. It verifies staging, publishes through the SDK, compares published source fingerprints
and settings with staging, and runs all seven published MCP isolation checks.

Preinstall `fabric-data-agent-sdk>=0.1.33a0,<0.2` and `mcp>=1,<2` in the notebook environment from
the approved package feed. The notebook never installs dependencies automatically. It enables and
reads back the preview runtime, follows source-element pagination, and resolves lakehouse tables
through the exact `Schemas` / `dbo` / `Tables` hierarchy rather than relying on element order.
Lakehouse examples must already use native T-SQL. Ontology V2 is semantic context, not a fourth
query datasource. The notebook never submits the rejected legacy ontology-as-datasource operation.
It refuses publication without independently reviewed native readiness evidence.

The configured draft can be tested without publishing it. The approved SDK's
`FabricOpenAIResponses` supports `ai_skill_stage="sandbox"` for this purpose. Keep sandbox
validation separate from the published MCP endpoint and retain the actual response IDs and
source-query run steps. Draft success does not satisfy the ontology-context, Topics,
model-owned Prep for AI, publication, or hosted/channel acceptance gates.

Fabric rejects native few-shot examples for semantic-model sources. Their DAX examples are
stored and read back in the data-source instructions field. Runtime evidence reports
`fewshot_count: 0`, `native_fewshots_supported: false`, and the separate
`instruction_example_count`; this is not a populated native Examples pane. These stored fields
do not prove that NL2DAX consumes the guidance. Microsoft documents semantic-model instructions
and verified answers as model-owned **Prep for AI** configuration, not supplemental Data Agent
source context. The user must review and apply these artifacts through Power BI's Prep for AI
experience. Do not author their persisted representation through TMDL or an undocumented API.
Model-side AI instructions and verified answers still require configuration and runtime
verification. See [supported source configurations](https://learn.microsoft.com/fabric/data-science/data-agent-add-datasources#configure-your-data-source).
Stored instruction examples do not satisfy model-owned readiness. SQL sources still require at least
ten distinct native examples each. Model readiness instead requires independently reviewed evidence
of model-owned instructions and at least ten Verified Answers, not an impossible semantic-model
native-few-shot count.

The notebook's `native_readiness_json` parameter is a retained review receipt, not a configuration
API or an automatic verification of the UI. Leave it empty until the actual native surfaces have
been configured and independently inspected. Never produce it from prepared repository content or
unchecked booleans. Its fields are:

- `workspaceId`, `dataAgentId`, and `draftDefinitionSha256`, bound to the exact current draft.
  `validate_only` returns the definition digest. A changed draft requires new verification.
- `ontologyContext`, bound by `artifactId` to the real ontology.
- `sqlTopics`, containing `HotelOperations` and `HotelGuestServices`, each bound to its lakehouse.
- `modelPrepForAI`, bound to the semantic model, with `instructionsConfigured: true` and the actual
  `verifiedAnswerCount`.

Each component records `verificationMethod: "native-ui-readback"`, an `evidenceRef` identifying its
retained native export or reviewed UI capture, and that artifact's `evidenceSha256`. These references
are operator attestations backed by retained evidence. Their presence does not itself establish that
the native configuration exists. The notebook checks the bindings and digest before any publication,
then verifies live native source selection, descriptions, examples, and published readback. Missing
or stale evidence stops the operation without rewriting the draft.

`schema-descriptions.json` contains portable business descriptions for the actual SQL source
tables and shared column meanings. These descriptions belong on native table/column overrides,
not only in an instructions-based dictionary. Topics are a separate preview SQL-source surface and
must be configured and verified there, not replaced with an instructions heading.
The source-specific Markdown in `topics/` is prepared content for that surface. Its presence in
the repository does not mean the live Topics pane has been populated or topic retrieval tested.
Topics are supported for directly mounted SQL sources on the preview runtime, not ontology-bound
sources. Inspect the actual source disposition after adding ontology context. If either lakehouse
becomes ontology-bound, stop and reconcile the release contract with that supported configuration.
Do not fabricate Topics evidence or relax the current publication gate to claim readiness.
See [source-specific configuration support](https://learn.microsoft.com/fabric/data-science/data-agent-add-datasources#configure-your-data-source).
SQL example files use native T-SQL, including `CAST(... AS date)` and `1` for `bit` predicates.

`draft/quality-gates.json` is the mandatory repository contract for source quality, acronyms,
business fixtures, and published-agent isolation tests. `scripts/fabric/cli.py` validates that all
selected source tables and fields appear in each source's data dictionary and that every source has
at least ten examples before any plan or deployment. Publication is successful only after the
notebook directly queries the published Data Agent MCP endpoint and all expected fixture terms are
returned, without involving the hosted hotel agent.
Reservation and stay answers include ISO 8601 dates alongside any localized date wording.
The nearest-reservation isolation question explicitly requests the confirmation identifier,
official property name, and internal property identifier, matching the fields it asserts.
Ordinary user-facing answers still resolve property identifiers to official names.
