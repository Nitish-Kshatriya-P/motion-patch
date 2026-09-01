# ADR 0001: Hybrid Modality for Error Detection & Cost Management

## Status
Proposed

## Context
We need a fast, cheap, and highly accurate way for the agent to detect motion capture anomalies (like foot sliding or jitter). 
- Feeding raw 3D coordinate text (BVH/FBX) to an LLM is expensive and yields low spatial reasoning accuracy. 
- Using video analysis on every frame of a movie is too expensive for a $300 budget.

## Decision
We will use a **Two-Pass "Heuristic + Multimodal" Pipeline**:
1. **Pass 1 (Deterministic & Free):** Fast, non-AI Python scripts scan the raw mocap data to flag *potential* regions of interest (ROI). For example, if a foot bone's Z-height is ~0 but its X/Y velocity is high, it flags a potential "foot slide". 
2. **Pass 2 (Agentic & Cheap):** We render *only* the flagged 3-to-5 second clips as low-res viewport video. We send this short video to **Gemini 2.5 Pro (Multimodal)** to visually confirm: *"Is this a foot slide, or a moonwalk?"*

## Consequences
- **Pros:** Drastically cuts token costs. Highly accurate because Gemini acts like a human director watching a screen.
- **Cons:** Requires building a fast viewport renderer and heuristic pipeline before the AI even kicks in.
