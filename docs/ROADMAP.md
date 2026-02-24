# Brightmind Roadmap and Near-Term Development

**Date:** 2026-02-24

## Current State
Brightmind local stack is operational in offline mode:
- Local gateway and inference verified
- OpenClaw adapter dry-run verified
- Readiness verifier and artifacts in place
- Live Slack/OpenClaw API integration intentionally deferred

## Roadmap (Next 7–14 Days)
### Day 0–2: Stabilization
1. Validate readiness script in repeatable runs
2. Capture baseline performance numbers (latency, CPU/RAM)
3. Add automated nightly readiness execution (optional)

### Day 3–5: Live Integration Prep
1. Configure Slack tokens locally in `.env`
2. Enable Socket Mode and verify mention/DM flow
3. Expand readiness checks to include Slack roundtrip

### Day 6–10: OpenClaw Live Mode
1. Switch adapter from dry-run to live mode
2. Validate OpenClaw calls through `/v1/chat/completions`
3. Document any required OpenClaw config fields

### Day 11–14: Hardening and Documentation
1. Improve logging structure and retention policy
2. Add log redaction checks for token leakage
3. Update security guardrails and incident steps

## Obstacles and Risks
1. **Token readiness**: Slack/OpenClaw tokens are not configured in offline mode.
2. **Port conflicts**: 8080/8081 may be occupied on some systems.
3. **Model size/VRAM**: 7B model is viable but may be slow on CPU-only runs.
4. **Doc drift**: OpenClaw/Slack docs can change; verify before enabling live modes.
5. **Ollama path issues**: `OLLAMA_MODELS` must remain on `D:` to avoid disk pressure.

## Areas for Further Development
1. **Performance**
   - Quantized 3B fallback or auto-select based on VRAM
   - Streaming responses in Slack UI
2. **Operational**
   - Optional service manager for start/stop
   - Metrics endpoint (latency, error rates)
3. **Security**
   - Log redaction filters
   - Optional outbound network allowlist
4. **Quality**
   - Unit tests for config parsing and gateway adapter
   - End-to-end tests for Slack integration

## Acceptance Criteria for Live Mode
1. Readiness report shows `live_integration_go=true`
2. Slack DM and @mention roundtrip within 5 seconds
3. Adapter live-mode path works without dry-run markers
4. No secrets appear in logs or artifacts
