# Hotel Guest Services Agent

This repository contains the source-controlled foundation for a fictional hotel guest-services demo built on Microsoft Foundry, Microsoft Fabric, Foundry IQ, Work IQ, and Agent 365.

The current bootstrap includes a container-ready Python Hosted Agent, generic technical naming enforcement, deployment configuration bound to the existing Foundry project, safe configuration examples, and reserved workstream directories. It does not contain the property corpus, generated business data, Fabric item definitions, indexes, or deployed cloud resources.

## Developer setup

Requirements:

- Python 3.13 or later
- Docker for container builds
- Azure Developer CLI with the `azure.ai.agents` extension for later deployment work

```bash
make setup
make check
```

Copy `.env.template` to `.env` for local Hosted Agent execution. Never commit `.env`, azd environment state, generated Agent 365 configuration, tokens, or deployment packages.

Run the agent after installing dependencies:

```bash
make run
```

Build the same root container shape used by Hosted Agent deployment:

```bash
make docker-build
```

The bootstrap exposes the Responses protocol. Phase 3 will add `invocations_ws` to the same agent and compose it over the shared `orchestration`, `tools`, and `state` packages.

See `PLAN.md` for the approved architecture and `DEPLOYMENT.md` for the controlled deployment handoff.
