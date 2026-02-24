# PRD: Brightmind Local Secure Runtime Guardrails (v1.0)

## 1. Objectives
- Safe-by-default local AI runtime for Brightmind.
- Deterministic startup + verification with go/no-go output.
- Least-privilege integration path for OpenClaw and Slack.

## 2. Scope
In scope:
- Local gateway and adapter lifecycle.
- Offline dry-run adapter validation.
- Security and operational guardrails.
- Readiness evidence artifacts.

Out of scope:
- Public internet exposure by default.
- Secret distribution systems beyond local `.env` handling.
- Multi-tenant policy enforcement.

## 3. Personas
- Local operator: wants one-command readiness verification.
- Developer: needs repeatable smoke tests.
- Security reviewer: needs traceable controls and incident response.

## 4. Architecture Overview
- `run_all.ps1` supervises core local services.
- `llm_gateway` serves `/health`, `/chat`, `/chat/stream`, `/models`.
- `openclaw_adapter` serves `/health`, `/v1/models`, `/v1/chat/completions`.
- `brightmind_stack_verify.ps1` orchestrates start/verify/smoke/report/stop.

Trust boundaries:
- Local host boundary (`127.0.0.1` only by default).
- Secrets boundary (`.env` local only, gitignored).
- Model runtime boundary (Ollama local service).

## 5. Threat Model (STRIDE-lite)
- Spoofing: invalid external callers if bound publicly.
  Control: localhost binding check, explicit fail on non-local bind.
- Tampering: config or scripts modified unexpectedly.
  Control: required file presence checks, report artifacts for audit.
- Repudiation: lack of evidence for pass/fail.
  Control: machine-readable readiness report with timestamp and evidence.
- Information disclosure: secrets in logs or command output.
  Control: no secret printing, token checks are format-only.
- Denial of service: model/runtime not available.
  Control: health loops, deterministic smoke tests, clear remediation.
- Elevation of privilege: accidental broad bind or unsafe clean-up.
  Control: localhost-only default, targeted process cleanup by repo path.

## 6. Security Controls
- Localhost-only default network policy.
- No inbound exposure unless explicit operator opt-in.
- Secrets in `.env`, never committed; `.env` remains ignored.
- Token validation is structural (`xoxb-`, `xapp-`) and non-disclosing.
- Log scanning for critical signatures in verification flow.

## 7. Operational SOPs
- Run `brightmind_stack_verify.ps1 -Command All` before task execution.
- Treat non-zero exit code as no-go.
- Review `artifacts/readiness/readiness_report.json` on every run.
- For unresolved failures, run diagnostics branch in runbook.

## 8. Logging and Retention
- Keep per-run artifacts under `artifacts/readiness/<timestamp>`.
- Retain last N runs (policy recommendation: 30 days local).
- Redact tokens before sharing logs externally.

## 9. Update and Patch Policy
- Check runtime/docs monthly or before enabling live integrations.
- Track Ollama and OpenClaw latest versions from official channels.
- Re-run full readiness suite after any runtime/script/model update.

## 10. Safe integration enablement policy
When enabling live API integrations later:
1. Set `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in local `.env`.
2. Keep adapter in `dry_run` until token checks pass and gateway smoke remains stable.
3. Enable live mode in a controlled session; rerun readiness and capture artifacts.
4. Rotate tokens if leakage suspected; never print tokens in terminal/logs.

## 11. Incident Playbook
- Severity 1 (critical fail): stop stack, collect artifacts, restore from known-good config.
- Severity 2 (smoke/perf fail): keep stack local, rerun with diagnostics and inspect logs.
- Severity 3 (integration unknown): proceed in local-only mode, defer live features.

## 12. Compliance Checklist
- [ ] Localhost binding verified
- [ ] No hardcoded secrets in repo
- [ ] Model availability verified
- [ ] Deterministic smoke tests passed
- [ ] Artifacts generated and reviewed
- [ ] Integration tokens deferred or configured safely

## 13. Sources and Recency
- OpenClaw docs: https://docs.openclaw.ai/ (last updated shown as 3 days ago; accessed 2026-02-24)
- OpenClaw Slack docs: https://docs.openclaw.ai/channels/slack (last updated shown as 3 days ago; accessed 2026-02-24)
- OpenClaw Ollama provider docs: https://docs.openclaw.ai/providers/ollama (last updated shown as 3 days ago; accessed 2026-02-24)
- OpenClaw npm package metadata: https://registry.npmjs.org/openclaw (`latest=2026.2.23`, published `2026-02-24T05:40:17Z`, modified `2026-02-24T05:40:18Z`)
- OpenClaw install endpoint: https://openclaw.ai/install.ps1 (accessed 2026-02-24)
- Slack Socket Mode docs: https://docs.slack.dev/apis/events-api/using-socket-mode (accessed 2026-02-24)
- Slack event `app_mention`: https://docs.slack.dev/reference/events/app_mention (accessed 2026-02-24)
- Slack scope `chat.write`: https://docs.slack.dev/reference/scopes/chat.write (accessed 2026-02-24)
- Slack scope `app_mentions.read`: https://docs.slack.dev/reference/scopes/app_mentions.read (accessed 2026-02-24)
- Ollama Windows docs: https://docs.ollama.com/windows (accessed 2026-02-24)
- Ollama FAQ (`OLLAMA_MODELS` behavior): https://docs.ollama.com/faq (accessed 2026-02-24)
- Ollama latest release metadata: https://api.github.com/repos/ollama/ollama/releases/latest (`v0.17.0`, published `2026-02-21T06:40:46Z`)
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html (accessed 2026-02-24)
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html (accessed 2026-02-24)
