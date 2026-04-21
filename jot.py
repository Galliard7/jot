#!/usr/bin/env python3
"""Jot list dispatcher — active list + 7-day archive of completed items.

Model:
- Active view (`/jot`): undone items + items done today (shown with green checkbox).
- Archive view (`/jot archive`): items done within the past ARCHIVE_DAYS, newest first.
- `done N` or `done <text>` marks by position or text match; item stays visible (green) until midnight.
- `undo N` / `undone N` restores by archive-view position. Bare `undo` restores the most recent.
- Auto-cleanup drops items whose done_date is older than ARCHIVE_DAYS days.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

DATA_PATH = os.path.expanduser("~/.openclaw/workspace/data/jot/jot.json")
CT = timezone(timedelta(hours=-5))
ARCHIVE_DAYS = 7


class JotError(ValueError):
    """User-facing errors printed at the main() boundary."""


def load():
    if not os.path.exists(DATA_PATH):
        return {"items": []}
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def save(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


def today_date():
    return datetime.now(CT).date()


def item_done_date(item):
    """Date an item was marked done, or None."""
    s = item.get("done_date")
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def item_done_at(item):
    """ISO timestamp an item was marked done, or None.
    Falls back to midnight of done_date for items marked before done_at was tracked."""
    s = item.get("done_at")
    if s:
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
    d = item_done_date(item)
    if d is not None:
        return datetime.combine(d, datetime.min.time(), tzinfo=CT)
    return None


def is_done(item):
    return item.get("done_date") is not None


def auto_clean(data):
    """Drop items marked done more than ARCHIVE_DAYS days ago."""
    cutoff = today_date() - timedelta(days=ARCHIVE_DAYS)
    before = len(data["items"])
    kept = [i for i in data["items"]
            if (d := item_done_date(i)) is None or d >= cutoff]
    if len(kept) != before:
        data["items"] = kept
        save(data)


def active_items(data):
    return [i for i in data["items"] if not is_done(i)]


def visible_items(data):
    """Items for the main list view: undone + done today."""
    today = today_date()
    return [i for i in data["items"]
            if not is_done(i) or item_done_date(i) == today]


def archive_items(data):
    """Done items within the past ARCHIVE_DAYS, newest first."""
    cutoff = today_date() - timedelta(days=ARCHIVE_DAYS)
    result = [i for i in data["items"]
              if (d := item_done_date(i)) is not None and d >= cutoff]
    result.sort(
        key=lambda i: item_done_at(i) or datetime.min.replace(tzinfo=CT),
        reverse=True,
    )
    return result


def cmd_list(data, show_numbers=False):
    items = visible_items(data)
    if not items:
        print("Jot list is empty.")
        return
    for i, item in enumerate(items, 1):
        icon = "\u2705" if is_done(item) else "\u2b1c"
        prefix = f"{i}. " if show_numbers else ""
        print(f"{prefix}{icon} {item['text']}")


def cmd_archive(data):
    items = archive_items(data)
    if not items:
        print("No items in archive (past 7 days).")
        return
    print("Archive (past 7 days, newest first):")
    for i, item in enumerate(items, 1):
        d = item_done_date(item)
        suffix = f"  [{d.isoformat()}]" if d else ""
        print(f"{i}. \u2705 {item['text']}{suffix}")


def cmd_add(data, text):
    item_id = uuid.uuid4().hex[:8]
    item = {
        "id": item_id,
        "text": text,
        "added_at": datetime.now(CT).isoformat(),
    }
    data["items"].append(item)
    save(data)
    print(f"Added: {text}")


def resolve_visible(data, number_or_text):
    """Return the item at 1-based visible-list position or by text match.
    Positions match what /jot shownum displays. Raises JotError on failure."""
    items = visible_items(data)
    # Try numeric position first.
    try:
        idx = int(number_or_text) - 1
        if 0 <= idx < len(items):
            return items[idx]
        raise JotError(f"No item at position {number_or_text}")
    except ValueError:
        pass
    # Fall back to case-insensitive text match (undone items only).
    undone = [i for i in items if not is_done(i)]
    query = number_or_text.lower()
    matches = [i for i in undone if query in i["text"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        lines = [f"  {j+1}. {m['text']}" for j, m in enumerate(matches)]
        raise JotError(f"Multiple matches for \"{number_or_text}\":\n" + "\n".join(lines)
                       + "\nUse a more specific term or position number.")
    raise JotError(f"No active item matching \"{number_or_text}\"")


def resolve_archive(data, number_str):
    """Return the item at 1-based archive-list position. Raises JotError on failure."""
    try:
        idx = int(number_str) - 1
    except ValueError:
        raise JotError(f"Invalid number: {number_str}")
    items = archive_items(data)
    if idx < 0 or idx >= len(items):
        raise JotError(f"No archive item at position {number_str}")
    return items[idx]


def cmd_done(data, args):
    # If all args are numbers, treat as batch positional (e.g., done 2 3).
    # Otherwise, join into a single text query (e.g., done test task).
    if all(a.isdigit() for a in args):
        to_mark = [resolve_visible(data, ns) for ns in args]
    else:
        to_mark = [resolve_visible(data, " ".join(args))]
    now = datetime.now(CT)
    for item in to_mark:
        item["done_date"] = now.date().isoformat()
        item["done_at"] = now.isoformat()
    save(data)
    for item in to_mark:
        print(f"Done: {item['text']}")


def cmd_undo(data, number_strs):
    """Restore archived item(s) to the active list.
    Bare undo (no args) restores the most recently done item."""
    if not number_strs:
        items = archive_items(data)
        if not items:
            print("Nothing to undo.")
            return
        item = items[0]
        item.pop("done_date", None)
        item.pop("done_at", None)
        save(data)
        print(f"Restored: {item['text']}")
        return
    to_restore = [resolve_archive(data, ns) for ns in number_strs]
    for item in to_restore:
        item.pop("done_date", None)
        item.pop("done_at", None)
    save(data)
    for item in to_restore:
        print(f"Restored: {item['text']}")


def cmd_remove(data, number_strs):
    """Permanently remove items from the active list."""
    to_remove = [resolve_visible(data, ns) for ns in number_strs]
    remove_ids = {item["id"] for item in to_remove}
    data["items"] = [i for i in data["items"] if i["id"] not in remove_ids]
    save(data)
    for item in to_remove:
        print(f"Removed: {item['text']}")


def cmd_edit(data, number_str, new_text):
    """Edit the text of an active item by position."""
    if not new_text.strip():
        print("Nothing to edit to — provide new text after the position number.")
        return
    item = resolve_visible(data, number_str)
    old_text = item["text"]
    item["text"] = new_text
    save(data)
    print(f"Edited {number_str}: {old_text} → {new_text}")


def cmd_help():
    print(
        "/jot <text>          — add a new item\n"
        "/jot                 — show list\n"
        "/jot shownum         — show list with position numbers\n"
        "/jot done <N...>     — mark done by position (batch: done 3 4 6)\n"
        "/jot done <text>     — mark done by text match\n"
        "/jot modify <N> <text> — edit item text\n"
        "/jot remove <N>      — permanently remove item\n"
        "/jot undo [N]        — restore last done (or by archive position)\n"
        "/jot archive         — show done items (past 7 days)\n"
        "/jot help            — show this help"
    )


def dispatch(data, args):
    if not args:
        cmd_list(data)
        return

    subcmd = args[0].lower()

    if subcmd == "help":
        cmd_help()
    elif subcmd == "done" and len(args) >= 2:
        cmd_done(data, args[1:])
    elif subcmd in ("undo", "undone"):
        cmd_undo(data, args[1:])
    elif subcmd in ("remove", "rm") and len(args) >= 2:
        cmd_remove(data, args[1:])
    elif subcmd in ("edit", "modify"):
        if len(args) < 2:
            print("Usage: modify <N> <new text>")
        elif len(args) < 3:
            print("Provide new text after the position number.")
        else:
            cmd_edit(data, args[1], " ".join(args[2:]))
    elif subcmd == "archive":
        cmd_archive(data)
    elif subcmd in ("list", "show"):
        cmd_list(data)
    elif subcmd == "shownum":
        cmd_list(data, show_numbers=True)
    else:
        cmd_add(data, " ".join(args))


def main():
    data = load()
    auto_clean(data)
    try:
        dispatch(data, sys.argv[1:])
    except JotError as e:
        print(e)


if __name__ == "__main__":
    main()
