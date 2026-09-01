# 06: Dynamic Multi-Agent Studio (Orchestrator & Experts)

**What to build:** Replace the monolithic single agent with a true multi-agent system. A Supervisor Agent interprets the audio/text prompt and routes it to the appropriate specialized expert (e.g., Kinematics Expert for jitter, Contact Expert for foot sliding). A QA Judge Agent intercepts the output script and validates it against physical constraints before sending it to the White-Box editor. 

**Blocked by:** 03, 04, 05

**Status:** ready-for-agent

- [ ] ADK Orchestrator/Supervisor agent implementation
- [ ] Specialized Worker Agents (Kinematics, Contact)
- [ ] QA Judge Agent with hard-check validation scripts
