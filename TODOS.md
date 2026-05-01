# TODOs

Small bugs and incremental improvements that don't deserve a full Phase in
`Mac-mini/PLAN.md`. Items here should be:

- Genuinely actionable (concrete enough to start without research)
- Small enough to land in one or two commits
- Real signal (an observed bug, a measurable defect, or a known security gap),
  not a "nice to have" that may never get done

When an item lands, delete its row. When you discover a new one, append it
with the date you noticed it (so we can tell what's gone stale).

For larger initiatives (new phases, new projects, refactors), use
`Mac-mini/PLAN.md`. For ideas without commitment, use the brainstorm file at
`~/.claude/plans/come-up-with-more-encapsulated-spring.md` (catalogued in
the `reference_macmini_brainstorm.md` memory).

---

## Open

| # | Noticed | Where | What |
|---|---|---|---|
| 1 | 2026-05-01 | `service-monitor/install.sh` ~line 60 | ollama-tracker idempotency check (`if launchctl list \| grep -q com.home-tools.ollama-tracker`) misses the already-loaded agent on reinstall, so it skips `unload` and the next `load` fails with `Load failed: 5: Input/output error`. Memory-tracker block (line 84) handles the same case correctly. Make the ollama block match memory-tracker's pattern (or DRY both into a shared shell function). |
| 2 | 2026-05-01 | event-aggregator | `com.home-tools.event-aggregator.worker` last exit was `-9` (SIGKILL) when checked 2026-05-01. Could be a manual `launchctl stop` from an earlier session, or memory pressure. Check `~/Home-Tools/logs/incidents.jsonl` for the timestamp + correlate with `memory_history.json` peak_pct. If recurring → underlying issue. If one-off → no action. |
| 3 | 2026-04-29 (Phase 5d audit) | mini sshd | `PasswordAuthentication yes` should be `no` for defense in depth. Tailscale SSH is identity-based; password fallback is a vestige. Edit `/etc/ssh/sshd_config` (or drop-in), `sudo launchctl kickstart -k system/com.openssh.sshd`. Verify Tailscale SSH still works after. |
| 4 | 2026-04-29 (Phase 5d audit) | mini smbd | `smbd` listening on `*:445` (mini is acting as an SMB server). Confirm intent — if unintentional, System Settings → General → Sharing → toggle off File Sharing. Check `sudo lsof -iTCP:445 -sTCP:LISTEN` to verify. |
| 5 | 2026-04-25+ | dispatcher | `dispatcher-error.log` has gone unread since 2026-04-25 per memory `project_dispatcher.md`. Read it; categorize errors; decide whether each warrants a fix or a log-level downgrade. |
| 6 | 2026-04-30 | `service-monitor/services.py` | If/when Pick 1 (Mini Jobs queue + console at :8503) lands, the existing event-aggregator `state.json` becomes contended between the dispatcher (writer) and the new console (writer). Add an exclusive file lock (`fcntl.flock` on a sentinel) before any write. |
| 7 | 2026-05-01 | `health-dashboard.staleness` | Last exit `1` when checked 2026-05-01. Likely cosmetic per `Mac-mini/PHASE6.md` (Python logging at INFO writes to stderr, launchd flags any stderr-write as non-zero). Confirm by tailing `~/Library/Logs/health-dashboard/staleness.log` after a run; if real, fix; if cosmetic, redirect logging to a file or stdout to silence the false-positive. |
| 8 | 2026-04-29 | `nas-intake/` | v2 deferreds: HEIC support, Slack hold-in-`_review` reactions on classifier mismatch, quarantine-after-N failures. Tracked in `nas-intake/README.md` "v1 limitations"; surface here if any becomes painful. |
| 9 | 2026-05-01 | Phase 7 backup verification | Quarterly: re-run `python3 Mac-mini/scripts/restic-restore-test.py` to confirm restores still work. Per `Mac-mini/RECOVERY.md` maintenance reminders. Could become a low-frequency LaunchAgent (e.g., 1st of each quarter at 04:30) if a real silent-restore-fail incident ever occurs; manual + calendar reminder is fine for v1. |
| 10 | 2026-05-01 | Phase 7 recovery posture | Yearly: print fresh paper copy of the 1Password "Mac mini home server recovery" Secure Note + store in fire safe / filing cabinet. Belt-and-suspenders against a 1Password-and-NAS-both-down scenario. Tied to a recurring calendar event is the lowest-friction path. |

---

## Recently closed (move from "Open" when done; trim after a few weeks)

- 2026-05-01 — Phase 7 NAS backup LIVE. 5 commits, 13/13 deploy gates passed. (commit `2fb1d00`)
- 2026-05-01 — `Mac-mini/scripts/preflight.py` drift checker added as canonical "is the mini in a consistent state?" gate. Replaces ad-hoc `launchctl list | grep`. (commit `8c26f84`)
- 2026-05-01 — Stale "11 LaunchAgents" claim removed from 3 docs; replaced with link to `services.py:SERVICES`. (commit `d360595`)
- 2026-05-01 — Orphan `event-aggregator/com.home-tools.event-aggregator.plist` deleted from repo. (commit `0fac7ce`)
