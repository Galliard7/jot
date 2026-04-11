#!/usr/bin/env python3
"""Jot list dispatcher — active list + 7-day archive of completed items.

Model:
- Active view (`/jot`): items not marked done.
- Archive view (`/jot archive`): items done within the past ARCHIVE_DAYS, newest first.
- `done N` marks by active-view position; the item vanishes from active immediately.
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


def cmd_list(data):
    items = active_items(data)
    if not items:
        print("Jot list is empty.")
        return
    for item in items:
        print(f"\u2b1c {item['text']}")


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


def resolve_active(data, number_str):
    """Return the item at 1-based active-list position. Raises JotError on failure."""
    try:
        idx = int(number_str) - 1
    except ValueError:
        raise JotError(f"Invalid number: {number_str}")
    items = active_items(data)
    if idx < 0 or idx >= len(items):
        raise JotError(f"No active item at position {number_str}")
    return items[idx]


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


def cmd_done(data, number_strs):
    # Resolve all before mutating so position shifts don't break batch operations.
    to_mark = [resolve_active(data, ns) for ns in number_strs]
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
    to_remove = [resolve_active(data, ns) for ns in number_strs]
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
    item = resolve_active(data, number_str)
    old_text = item["text"]
    item["text"] = new_text
    save(data)
    print(f"Edited {number_str}: {old_text} → {new_text}")


def dispatch(data, args):
    if not args:
        cmd_list(data)
        return

    subcmd = args[0].lower()

    if subcmd == "done" and len(args) >= 2:
        cmd_done(data, args[1:])
    elif subcmd in ("undo", "undone"):
        cmd_undo(data, args[1:])
    elif subcmd in ("remove", "rm") and len(args) >= 2:
        cmd_remove(data, args[1:])
    elif subcmd == "edit":
        if len(args) < 2:
            print("Usage: edit <N> <new text>")
        elif len(args) < 3:
            print("Provide new text after the position number.")
        else:
            cmd_edit(data, args[1], " ".join(args[2:]))
    elif subcmd == "archive":
        cmd_archive(data)
    elif subcmd in ("list", "show"):
        cmd_list(data)
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
