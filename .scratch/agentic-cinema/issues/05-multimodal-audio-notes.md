# 05: Multimodal Audio Director's Notes

**What to build:** Maximize the "wow" factor. Add a "Hold to Speak" button to the UI that captures audio using the browser's `MediaRecorder`. The audio blob is sent to the backend and passed as a direct multimodal input to Gemini 1.5 Pro via ADK, replacing/augmenting the text prompt so animators can just speak their fixes.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] React UI component for "Hold to Speak" audio recording
- [ ] Backend handling of `.webm`/`.mp3` blobs
- [ ] ADK configuration updated to process raw multimodal audio alongside the `.bvh` context
