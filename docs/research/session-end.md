# How does a session end, and how could a drive tell?

Research for #39, under map #38 (drive a spec). This is facts with sources, not a design.
Checked 2026-10-02 against Claude Code 2.1.288, tmux 3.7c and gh 2.100.0 on Jeff's Mac.

## Short answer

A session that `board work` starts **does not exit when the work is done**. Claude Code
in interactive mode has no way to end its own session on finishing a task. The only
tool that ends a session, `EndConversation`, is reserved for abuse. Nothing in
`/mattpocock-skills:implement` asks for an exit either. A finished session sits idle at
the prompt, and its tmux window stays open until someone or something kills it. The
windows for #32, #33 and #34 vanished for some reason outside Claude: their transcripts
end idle, and none records an `/exit`.

The `Stop` hook fires at the end of **every turn**, not just at the end of the ticket.
It doesn't say whether the ticket landed, whether the session is waiting on the human,
or whether it gave up. It does carry the final text (`last_assistant_message`) and any
in-flight `background_tasks`. The decisive signal for "landed" is GitHub: the issue is
`CLOSED`/`COMPLETED` with `closedByPullRequestsReferences`. Headless `claude -p` does
exit when the work is done, with an exit code and a JSON `result`. You can't watch or
answer it, though, which conflicts with the **Session** definition in `CONTEXT.md`.

## 1. How board starts a session today

- `start_sessions` runs `claude --dangerously-skip-permissions "/mattpocock-skills:implement N"` as the
  command of a new tmux window named `#N`, in a tmux session named after the repo
  (`src/board/work.py`, `open_window`; `src/board/route.py` `STARTS`).
- The window's only process is `claude`. When claude exits, the window's program has exited
  (see §4 for what tmux then does).
- `live_windows` (`src/board/worktree.py`) lists window names via
  `tmux list-windows -t =<repo> -F '#{window_name}'`. A missing window with a surviving
  worktree is reopened with `claude --continue` (`go_back` in `work.py`).

## 2. What the implement skill tells the agent

`~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/implement/SKILL.md`
in full: implement the spec or tickets, use `/tdd`, typecheck, run the suite, `/code-review`,
"Commit your work to the current branch." It says **nothing about pushing, a PR, merging
or exiting**. Landing comes from the repo's workflow (`../waystation/CLAUDE.md`, "Green means
land it… `gh pr merge <n> --merge --delete-branch`"), not from the skill.

## 3. Does an interactive session exit when the work finishes? No

- `claude "query"` means "Start interactive session with initial prompt"
  ([CLI reference](https://code.claude.com/docs/en/cli-reference)). After the turn it
  waits for the next prompt.
- The only tool that ends a session is `EndConversation`, and Claude uses it "only in two
  situations": sustained abusive input, or when you ask to see it demonstrated.
  "General frustration… or a task going badly don't qualify." Once it's used, the session
  *locks*: it doesn't exit, and only `/clear`, `/resume`, `/help`, `/exit` and `/feedback` still
  run ([tools reference, EndConversation](https://code.claude.com/docs/en/tools-reference#endconversation-tool-behavior)).
- **Observed on #32, #33, #34.** Script over
  `~/.claude/projects/-Users-jeffrichley-workspaces-ai-dev-board-worktrees-{32,33,34}/*.jsonl`:

  | Ticket | PR merged (gh) | Agent's own end | Later human prompt | `/exit` in transcript |
  | - | - | - | - | - |
  | #32 | #35 at 00:14:50Z | Stop 00:15:00Z | 00:40 "is it pushed to main?" | none |
  | #33 | #36 at 00:16:20Z | Stop 00:16:28Z | 00:41 "is it on main or still blocked" | none |
  | #34 | #37 at 00:52:17Z | Stop 00:48:20Z, *"I haven't pushed or opened a PR yet"* | 00:51 "yes and get it to main" | none |

  Each session idled after its last turn. Each one had 4 `Stop` events in total.
  A `/exit` is recorded in a transcript as `<command-name>/exit</command-name>`. Other
  transcripts on this machine contain it, and these three don't. So the windows were closed
  from outside, for example by ⌘W on an iTerm2 `-CC` tab, which kills the tmux window
  (user memory note), or by a tmux server or session being killed. The `board` tmux session
  no longer exists (`tmux list-windows -a` shows only `wayfarer` and `waystation`).
- **#34 matters.** The agent stopped short of landing, which goes against the workflow's
  "green means land it". It sat idle with the ticket open until a human answered. "Idle"
  therefore doesn't mean "landed".

## 4. tmux: what happens when the window's command exits

From `man tmux` (3.7c) and local `tmux show-options`:

- `remain-on-exit [on | off | failed | key]`: "A pane with this flag set is not destroyed
  when the program running in it exits." `failed` keeps it only on a non-zero status. It is
  `off` here, so **a window whose claude exits disappears**. Locally both
  `show-options -g` and `-gw` give `remain-on-exit off`.
- With `remain-on-exit on`, the dead pane stays and exposes `#{pane_dead}`,
  `#{pane_dead_status}` (exit status), `#{pane_dead_signal}` and `#{pane_dead_time}`. The
  `pane-died` hook fires ("program exits, but remain-on-exit is on"). `pane-exited`
  fires whenever the program exits.
- When a session's last window goes, the session goes with it. `exit-empty on` (the default)
  stops the server when no sessions remain.
- Idle detection is also available: `#{window_activity}` (time of last output),
  `monitor-silence <seconds>`, the `alert-silence` hook and `#{window_silence_flag}`.
  `#{pane_current_command}` names the foreground process. It reported `claude.exe` for
  a live session here.

## 5. Hooks: what fires when, and what it carries

Source: [Hooks reference](https://code.claude.com/docs/en/hooks). All events carry
`session_id`, `transcript_path`, `cwd` and `hook_event_name`, and `permission_mode` on most.

- **Stop**: "when the main Claude Code agent has finished responding". It fires per
  *turn*, not per session, and "Does not run if the stoppage occurred due to a user
  interrupt". It carries `stop_hook_active`, `last_assistant_message` (the final text),
  `background_tasks` (in-flight shell/subagent/monitor/workflow tasks: `id`, `type`, `status`,
  `description`…) and `session_crons`. Per the docs, these two arrays "let hooks distinguish
  'session is done' from 'session is paused waiting for background work to wake it back up'".
  Decision control: `{"decision":"block","reason":…}` or exit code 2 keeps Claude going, with
  `reason` as its next instruction. Capped at 8 consecutive continuations
  (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). *Observed:* in #32–#34, Stop fired while background
  review subagents were still running, and fired again when their `<task-notification>`
  woke the session.
- **StopFailure**: fires *instead of* Stop when the turn ends on an API error. It carries
  `error` (`rate_limit`, `overloaded`, `authentication_failed`, `billing_error`,
  `server_error`, `max_output_tokens`, …, `unknown`), `error_details` and
  `last_assistant_message` (the error string). It has no decision control.
- **SubagentStop**: when a subagent finishes. It carries `agent_id`, `agent_type`,
  `agent_transcript_path` and `last_assistant_message`. It also fires for Claude Code's
  internal agents (prompt suggestions, `/btw`) with an empty `agent_type`. Not a
  session-end signal.
- **Notification**: carries `message`, optional `title` and `notification_type`. Types that
  bear on this: `permission_prompt` (after about 6 s unanswered), `idle_prompt` ("Claude finished
  responding about 60 seconds ago and you haven't typed since", and **not** sent while a
  background agent is still running), `elicitation_dialog`, and the
  `quota_auto_resume_fired`/`_stale`/`_disabled` usage-limit types. It can't block.
  The docs say: "in terminal sessions you only see them when you appear to be away".
- **SessionEnd**: "When a session terminates". It carries `reason`: `clear`, `resume`,
  `logout`, `prompt_input_exit` ("User exited while prompt input was visible") or `other`.
  It can't block, and its default timeout is 1.5 s.
- **PermissionRequest**: fires immediately when a permission prompt would show. Board
  sessions run with `--dangerously-skip-permissions`, so it's mostly moot.

**Can a hook tell landed / waiting on human / gave up apart?** Not from any field. No hook
payload carries an outcome. "Landed" exists only on GitHub. "Waiting on the human" and
"gave up" both look like `Stop` with empty `background_tasks`, followed by `idle_prompt`
about 60 s later. Only the wording of `last_assistant_message` tells them apart (#34's
"I haven't pushed or opened a PR yet"). `StopFailure` is the one structured "couldn't
continue" signal, and it covers API errors only.

Where hooks can come from (same doc, "Hook locations" / CLI reference): user, project and
local settings, plugins, skills/agents frontmatter, and `--settings <file-or-json>` per
invocation. With the last one, board could attach hooks to only the sessions it starts.
Jeff's `~/.claude/settings.json` already runs `~/.config/iterm2/cc-status` (a binary) on
Stop, StopFailure, SessionEnd, Notification and others.

## 6. Headless / non-interactive options

Source: [Run Claude Code programmatically](https://code.claude.com/docs/en/headless), CLI reference,
[Agent SDK TypeScript](https://code.claude.com/docs/en/agent-sdk/typescript).

- `claude -p "<prompt>"` runs non-interactively and **exits**: "exits with code 0 on success
  and a non-zero code when the run fails". Slash commands and skills work in `-p`
  ("Include `/skill-name` in the prompt string").
- `--output-format json` gives a final `result` object with `session_id`, `is_error`,
  `num_turns`, `result` (text) and `stop_reason`. Its `subtype` is `success` or
  `error_max_turns`, `error_during_execution`, `error_max_budget_usd` or
  `error_max_structured_output_retries`. `stream-json` streams every event, and with
  `--include-hook-events` it also streams hook events.
- `-p` waits for background subagents or workflows before exiting, up to a 10-min idle
  ceiling (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`). SIGTERM gives exit 143 and runs
  SessionEnd.
- `--max-turns` and `--max-budget-usd` are print mode only, and exit with an error at the limit.
- `--resume <session-id>` / `--continue` can pick a `-p` run back up, interactively or not.
  `--session-id <uuid>` presets the ID. **Caveat:** interactive `--continue` "Skips sessions
  created with `claude -p`". To reopen a `-p` session interactively, use `--resume <id>`.
- In `-p`, nobody can answer a question. A permission prompt or `AskUserQuestion` has no
  human. This conflicts with **Session** in `CONTEXT.md` ("You can watch and answer it while
  it runs").
- Also available, but not investigated in depth: `claude --bg` background sessions, and
  `claude agents --json [--all]` listing active and completed background sessions. The
  `agent_completed` / `agent_needs_input` notification types fire only while agent view is
  open.

## 7. What `gh` exposes

From `gh issue view --help` / `gh pr view --help` (2.100.0), checked against #34 and PR #37:

- Issue: `state` (`OPEN`/`CLOSED`), `stateReason` (`COMPLETED`, `NOT_PLANNED`…; empty while
  open), `closedAt`, `closedByPullRequestsReferences` (the PR that closed it; #34 gives `[#37]`),
  `assignees` (the claim), `blockedBy`, `blocking`, `parent`, `subIssues`, `subIssuesSummary`.
- PR: `state`, `mergedAt`, `mergedBy`, `closingIssuesReferences`, `statusCheckRollup`,
  `mergeStateStatus`, `headRefName`, `isDraft`, `autoMergeRequest`.
- Issue #34 closed at 00:52:18Z, one second after PR #37 merged at 00:52:17Z. Landing does
  close the ticket.

## What a watcher could read, at a glance

| Signal | Says | Doesn't say |
| - | - | - |
| Issue `CLOSED` + `closedByPullRequestsReferences` (gh) | Ticket landed | Anything about the session |
| Branch / open PR / `statusCheckRollup` (gh) | How far toward landing it got | Why it stopped |
| `Stop` hook with empty `background_tasks` | The turn ended, nothing in flight | Landed vs waiting vs gave up |
| `Notification` `idle_prompt` | Idle for 60 s, no human typed, no background agents | Same |
| `StopFailure` | API error ended the turn (typed `error`) | — |
| `SessionEnd` `reason` | The claude process is ending | Outcome |
| tmux window gone (`live_windows`) | claude exited or the window was killed | Which, or why (`remain-on-exit off`) |
| `pane_dead_status` (needs `remain-on-exit on`) | claude's exit code | Outcome of an interactive run |
| `window_activity` / `monitor-silence` | Output stopped | Why |
| `claude -p` exit code + JSON `subtype` | Run succeeded or errored (max turns, budget, execution) | Whether the ticket landed |
