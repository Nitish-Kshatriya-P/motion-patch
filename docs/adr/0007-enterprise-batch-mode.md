# ADR 0007: Enterprise Batch Processing

## Status
Proposed

## Context
To maximize our score on "Potential Impact / Enterprise Viability", we need to prove the system can handle the scale of a real studio (which processes thousands of mocap files a day, not just one at a time via a web dashboard). However, processing thousands of files during a hackathon demo would exhaust our $300 budget in Gemini API tokens.

## Decision
We will build an asynchronous **Batch Mode** into our architecture.
1. **UI:** The React dashboard will allow users to upload a ZIP of multiple BVH files.
2. **Infrastructure:** We will use **Google Cloud Run Jobs** to spin up parallel dynamic agents to process the files concurrently.
3. **Budget Guardrail:** For the hackathon demo, the system will be artificially capped to process a maximum of **5 files** per batch. 

## Consequences
- **Pros:** Proves enterprise scalability to the judges. Completely protects our limited token budget during live demos and testing.
- **Cons:** Slightly more complex backend routing to handle concurrent file processing and aggregating the results back to the dashboard.
