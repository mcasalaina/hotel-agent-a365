# Foundry evaluator rubrics

Use a rubric generation job to create the evaluator catalog entry before adding hand-edited
versions. Calling `create_version` first can create a version that is retrievable by exact name and
version but is absent from the evaluator catalog and invisible in the Foundry portal.

## Current hotel rubric

- Project: `4iq-foundry-project`
- Endpoint:
  `https://4iq-foundry-project-resource.services.ai.azure.com/api/projects/4iq-foundry-project`
- Resource name: `hotel-agent-rubric`
- Display name: `Hotel Servicing Rubric`
- Evaluator configuration: `eval.yaml`
- Judge model: `gpt-5.4-mini`
- Pass threshold: `0.68`

The rubric has 13 dimensions derived from `agent-instructions.md`. Its weights use three explicit
tiers:

- `10`: safety and data-integrity boundaries
- `6`: task correctness
- `3`: interaction quality

This avoids assigning a different subjective weight to every requirement.

## Why the first attempt did not appear

`AIProjectClient.beta.evaluators.create_version` accepted a new rubric before an evaluator parent
existed. `get_version(name, version)` returned the created object, which made the operation look
successful. The catalog APIs still returned no evaluator:

```text
list() -> []
list_versions("hotel-agent-rubric") -> evaluator not found
```

The portal uses the catalog index, not direct version lookup, so the orphaned version did not
appear. A successful `get_version` call is not enough to prove that an evaluator is portal-visible.

## Catalog-visible creation sequence

Use `azure-ai-projects>=2.2.0`. Version 2.3.0 was used for this project.

1. Submit an `EvaluatorGenerationJob` with the final resource name, display name, judge model, and a
   prompt source based on the agent instructions.
2. Poll `get_generation_job` until it returns `succeeded`.
3. Use the generated evaluator as version 1. This step creates the evaluator parent and catalog
   index.
4. Call `create_version` to add the reviewed, hand-edited dimensions as version 2 or later.
5. Poll `list(type="custom")` and `list_versions(name)` until the newest version appears.
6. Delete temporary bootstrap evaluators and superseded versions after the reviewed version is
   visible.

The core SDK pattern is:

```python
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    EvaluatorGenerationInputs,
    EvaluatorGenerationJob,
    JobStatus,
    PromptEvaluatorGenerationJobSource,
)
from azure.identity import AzureCliCredential

endpoint = (
    "https://4iq-foundry-project-resource.services.ai.azure.com"
    "/api/projects/4iq-foundry-project"
)
name = "hotel-agent-rubric"

with (
    AzureCliCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as client,
):
    job = client.beta.evaluators.create_generation_job(
        job=EvaluatorGenerationJob(
            inputs=EvaluatorGenerationInputs(
                model="gpt-5.4-mini",
                evaluator_name=name,
                evaluator_display_name="Hotel Servicing Rubric",
                evaluator_description="Domain rubric for hotel guest servicing quality.",
                sources=[
                    PromptEvaluatorGenerationJobSource(
                        description="Hotel agent instructions and behavioral contracts.",
                        prompt=open("agent-instructions.md", encoding="utf-8").read(),
                    )
                ],
            )
        )
    )

    while job.status not in {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }:
        time.sleep(10)
        job = client.beta.evaluators.get_generation_job(job.id)

    if job.status != JobStatus.SUCCEEDED:
        raise RuntimeError(job.error.message if job.error else str(job.status))

    reviewed = client.beta.evaluators.create_version(
        name=name,
        evaluator_version={
            "name": name,
            "categories": ["quality"],
            "display_name": "Hotel Servicing Rubric",
            "description": "Domain rubric for hotel guest servicing quality.",
            "definition": {
                "type": "rubric",
                "dimensions": reviewed_dimensions,
                "pass_threshold": 0.68,
            },
        },
    )
```

`reviewed_dimensions` must preserve the generated `general_quality` dimension as always applicable.
The other dimensions can be replaced with the reviewed domain criteria.

## Portal verification

Wait 30 to 90 seconds after creating or deleting a version, then verify both catalog surfaces:

```python
catalog = list(client.beta.evaluators.list(type="custom"))
versions = list(client.beta.evaluators.list_versions("hotel-agent-rubric"))
```

The rubric is ready only when:

- `list(type="custom")` contains `hotel-agent-rubric`
- `list_versions("hotel-agent-rubric")` contains the reviewed version
- the latest catalog entry reports 13 dimensions
- the portal search finds `Hotel Servicing Rubric`

The portal can retain an older version while indexing catches up. Refresh after the catalog API
returns the new version. Delete obsolete versions if operators should not be able to select them.

## `azd ai agent eval generate` behavior

`azd ai agent eval generate` creates both a dataset generation job and an evaluator generation job.
It also writes `.agent_configs/` and a local azd log. Use it when both assets are wanted. For a
rubric-only change, use `EvaluatorGenerationJob` directly.

If `azd` is used, give `--name` the final human-readable suite name. Do not use temporary names such
as `*-bootstrap`, because generated evaluator names can appear in the portal catalog.

Generated evaluator, dataset, suite, and result caches under
`src/hotel-servicing-agent/.foundry/` are intentionally ignored except for their README files.
`eval.yaml` is the source-controlled binding to the evaluator resource name.
