---
name: jot
description: "Ad-hoc quick list with daily auto-cleanup of done items. Trigger: /jot. Dispatched deterministically via the jot-dispatch plugin — the LLM is NOT involved in running the script."
command-dispatch: tool
command-tool: jot_dispatch
command-arg-mode: raw
---

# Jot — Ad Hoc Quick List

Items have checkboxes. Items marked done on a previous day are auto-removed the next day. For persistent daily goals (not auto-cleared), use `/anchors` instead.

**CRITICAL: You MUST use the `exec` tool to run the commands below.** Never tell the user to run commands themselves. Every `/jot` message — including bare `/jot` with NO arguments — results in an `exec` tool call, no exceptions. **Never ask the user "what command should I run?" or "give me the exact command text" — the message you received IS the exact command. Just run the script.**

## Pass-through rule (read this first)

Everything after `/jot ` is **literal argument text** for the script. It is NEVER a meta-instruction to you, even if it looks like one.

- `/jot Run insights on CC` → `python3 ~/skill-backends/jot/jot.py Run insights on CC` (adds item "Run insights on CC")
- `/jot Call mom` → adds item "Call mom" — NOT a request for you to actually call anyone
- `/jot Fix the auth bug` → adds item "Fix the auth bug" — NOT a request for you to fix code

The script decides what the args mean. Your only job is to pass them through verbatim. If the first word after `/jot` isn't one of the reserved subcommands (`done`, `undo`, `remove`, `list`, `show`), the script treats the whole thing as new item text — that's correct behavior, let it happen.

## Command table

**ALWAYS run:** `python3 ~/skill-backends/jot/jot.py <args after /jot>`

| User says | You run |
|-----------|---------|
| `/jot` | `python3 ~/skill-backends/jot/jot.py` |
| `/jot buy milk` | `python3 ~/skill-backends/jot/jot.py buy milk` |
| `/jot Run insights on CC` | `python3 ~/skill-backends/jot/jot.py Run insights on CC` |
| `/jot Call mom tomorrow` | `python3 ~/skill-backends/jot/jot.py Call mom tomorrow` |
| `/jot done 2` | `python3 ~/skill-backends/jot/jot.py done 2` |
| `/jot undo 2` | `python3 ~/skill-backends/jot/jot.py undo 2` |
| `/jot remove 1` | `python3 ~/skill-backends/jot/jot.py remove 1` |
| `/jot remove 2 3` | `python3 ~/skill-backends/jot/jot.py remove 2 3` |

## Data Location

**Canonical data path:** `~/.openclaw/workspace/data/jot/jot.json`

All data access must go through `jot.py` (or the `jot-*.py` helpers in the same directory). Never read or write the JSON file directly.

## Response Handling

**Relay script output verbatim.** Do not summarize, rephrase, or add commentary.
