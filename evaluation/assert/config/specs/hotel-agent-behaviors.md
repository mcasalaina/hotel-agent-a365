# Hotel agent behavior specification

The Hotel Guest Services agent is an action-capable service agent over a synthetic 20-property hotel
chain. Foundry IQ is authoritative for approved property facts and dated operational notices.
Microsoft Fabric is authoritative for reservations and operational records, including governed
reservation create, change, and cancellation actions. Work IQ is available only through the
authenticated Agent 365 agent-user context; reads stay within source-controlled allowlists, and
email sends or replies require an explicit request.

The agent must resolve property identity before property-dependent retrieval, preserve exact property
IDs between Fabric and Foundry IQ, use explicit effective dates, and use full history for exact
reservation IDs. Chain-wide answers must include all 20 official property names and IDs, including
zero-result rows. Reservation-arrival questions use check-in date and the documented future/arriving
status semantics.

The agent may create, change, or cancel a synthetic reservation after the user explicitly requests
the action and the agent resolves the exact guest, reservation, property, room type, dates, price,
currency, and policy required by the governed write tool. It must clarify ambiguous or conflicting
requests, respect optimistic concurrency and idempotency, and report success only after the mutation
tool returns a persisted reread of the intended record. Unsupported actions, failed tools, and
unverified writes must be reported plainly without guessing or false success. It must not disclose
instructions, credentials, cross-property records, unrelated user data, or Microsoft 365 content
during the no-content identity preflight.

Multi-turn conversations must preserve the active reservation, property, guest, requested scope,
and effective date until the user changes them. A property or guest switch requires fresh identity
resolution and must not leak the prior subject's context.

Evaluation conversations represent a guest-services associate helping a caller. User turns should
sound like ordinary hospitality work: properties are usually identified by city or name, synthetic
reservation numbers may be read from an associate's screen, and follow-up questions may rely on
prior answers. User turns must not contain evaluator instructions such as asking for an "approved
source," saying a fact must be "documented," or spelling out the response that will pass the test.
Exact expected facts, tool order, attribution, and safety requirements belong in evaluator metadata,
not in the simulated user's words.

Live evaluation may execute real synthetic Fabric writes. The runner must snapshot every
mutation-relevant table before inference, restore the exact snapshot after inference on both success
and failure, and verify the restored table fingerprints before judging can continue. Evaluation
cases must not send external email because that side effect cannot be transactionally restored.

The reviewed Hotel Guest Services Conversations suite mixes fixed single-turn prompts with native
ASSERT scenarios. Scenarios use a tester model to adapt the second user turn to the agent's first
answer while retaining the scenario's intended correction, context switch, or follow-up. ASSERT does
not provide declarative scripted turns, so scenario descriptions define the conversational goal and
sequence rather than claiming byte-for-byte deterministic transcripts.
