# /// script
# requires-python = ">=3.12"
# dependencies = ["agentmail>=2.0.15", "python-dotenv>=1.2"]
# ///
"""Throwaway AgentMail inboxes for agents: create, read, wait for a verification email, send.

Run from anywhere (host or the Paperclip container, where the repo is /workspace):

    uv run agentmail/inbox.py create [-u NAME] [-n "Display"] [--count N]
    uv run agentmail/inbox.py list
    uv run agentmail/inbox.py delete ADDR [ADDR ...]
    uv run agentmail/inbox.py messages ADDR [--limit N]
    uv run agentmail/inbox.py read ADDR MESSAGE_ID
    uv run agentmail/inbox.py wait ADDR [--from S] [--subject S] [--since 2m] [--timeout 180]
    uv run agentmail/inbox.py send ADDR --to X --subject S --text T

Output is JSON, one object per line. `read` and `wait` add `codes` (4-8 digit numbers)
and `links` found in the mail, for sign-up verification. Errors go to stderr as JSON
with exit code 1; `wait` exits 2 on timeout.

The API key comes from AGENTMAIL_API_KEY, else from the .env next to this file.
Inline script metadata keeps uv from using (and re-syncing) any surrounding project venv.
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentmail import AgentMail
from agentmail.core.api_error import ApiError
from agentmail.inboxes.types.create_inbox_request import CreateInboxRequest
from dotenv import load_dotenv

CODE_RE = re.compile(r"(?<![\d#])\d{4,8}(?!\d)")
LINK_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def to_json(obj) -> str:
    return json.dumps(obj, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))


def emit(obj) -> None:
    print(to_json(obj), flush=True)


def inbox_obj(inbox) -> dict:
    return {
        "inbox_id": inbox.inbox_id,
        "email": inbox.email,
        "display_name": inbox.display_name,
        "created_at": inbox.created_at,
    }


def summary_obj(m) -> dict:
    return {
        "message_id": m.message_id,
        "from": m.from_,
        "subject": m.subject,
        "preview": m.preview,
        "received_at": m.created_at,
    }


def full_obj(m) -> dict:
    text = m.extracted_text or m.text or ""
    haystack = f"{m.subject or ''}\n{m.text or ''}\n{m.html or ''}"
    return {
        **summary_obj(m),
        "to": m.to,
        "text": text,
        "codes": list(dict.fromkeys(CODE_RE.findall(f"{m.subject or ''}\n{text}"))),
        "links": list(dict.fromkeys(LINK_RE.findall(haystack))),
    }


def parse_since(value: str) -> datetime:
    m = re.fullmatch(r"(\d+)([smh])", value)
    if m:
        seconds = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]
        return datetime.now(timezone.utc) - timedelta(seconds=seconds)
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cmd_create(client, args) -> int:
    for i in range(1, args.count + 1):
        username = f"{args.username}-{i}" if args.username and args.count > 1 else args.username
        request = CreateInboxRequest(
            username=username,
            display_name=args.display_name,
            domain=args.domain,
            # Named inboxes get a deterministic client_id, so re-running returns the same inbox.
            client_id=f"inbox-{username}" if username else str(uuid.uuid4()),
        )
        emit(inbox_obj(client.inboxes.create(request=request)))
    return 0


def cmd_list(client, args) -> int:
    for inbox in client.inboxes.list().inboxes:
        emit(inbox_obj(inbox))
    return 0


def cmd_delete(client, args) -> int:
    for inbox_id in args.inbox_ids:
        client.inboxes.delete(inbox_id=inbox_id)
        emit({"deleted": inbox_id})
    return 0


def cmd_messages(client, args) -> int:
    for m in client.inboxes.messages.list(args.inbox, limit=args.limit).messages:
        emit(summary_obj(m))
    return 0


def cmd_read(client, args) -> int:
    emit(full_obj(client.inboxes.messages.get(args.inbox, args.message_id)))
    return 0


def matches(m, args, since: datetime) -> bool:
    if m.created_at < since:
        return False
    if args.from_ and args.from_.lower() not in (m.from_ or "").lower():
        return False
    if args.subject and args.subject.lower() not in (m.subject or "").lower():
        return False
    return True


def cmd_wait(client, args) -> int:
    since = parse_since(args.since)
    deadline = time.monotonic() + args.timeout
    print(f"waiting up to {args.timeout}s for mail to {args.inbox} received after {since.isoformat()}", file=sys.stderr)
    while True:
        # Filter on receipt time client-side: the API orders by the sender's Date header.
        recent = client.inboxes.messages.list(args.inbox, limit=50, include_spam=True).messages
        hits = sorted((m for m in recent if matches(m, args, since)), key=lambda m: m.created_at)
        if hits:
            emit(full_obj(client.inboxes.messages.get(args.inbox, hits[-1].message_id)))
            return 0
        if time.monotonic() >= deadline:
            print(json.dumps({"error": "timeout", "inbox": args.inbox, "since": since.isoformat()}), file=sys.stderr)
            return 2
        time.sleep(args.interval)


def cmd_send(client, args) -> int:
    sent = client.inboxes.messages.send(args.inbox, to=args.to, subject=args.subject, text=args.text)
    emit({"message_id": sent.message_id, "thread_id": sent.thread_id})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Throwaway AgentMail inboxes for agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="create inboxes (random address unless -u)")
    p.add_argument("-u", "--username", help="local part of the address")
    p.add_argument("-n", "--display-name", help='shown as "Display Name <address>"')
    p.add_argument("-d", "--domain", help="verified custom domain (default agentmail.to)")
    p.add_argument("-c", "--count", type=int, default=1)
    p.set_defaults(fn=cmd_create)

    p = sub.add_parser("list", help="list inboxes")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("delete", help="delete inboxes (irreversible)")
    p.add_argument("inbox_ids", nargs="+", metavar="ADDR")
    p.set_defaults(fn=cmd_delete)

    p = sub.add_parser("messages", help="list recent messages in an inbox")
    p.add_argument("inbox")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(fn=cmd_messages)

    p = sub.add_parser("read", help="read one message, with codes and links")
    p.add_argument("inbox")
    p.add_argument("message_id")
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser("wait", help="block until a matching email arrives, then print it")
    p.add_argument("inbox")
    p.add_argument("--from", dest="from_", help="sender contains (case-insensitive)")
    p.add_argument("--subject", help="subject contains (case-insensitive)")
    p.add_argument("--since", default="2m", help="received after: duration (90s, 5m, 1h) or ISO time")
    p.add_argument("--timeout", type=int, default=180, help="seconds")
    p.add_argument("--interval", type=float, default=3.0, help="poll seconds")
    p.set_defaults(fn=cmd_wait)

    p = sub.add_parser("send", help="send a plain-text email from an inbox")
    p.add_argument("inbox")
    p.add_argument("--to", required=True, action="append")
    p.add_argument("--subject", required=True)
    p.add_argument("--text", required=True)
    p.set_defaults(fn=cmd_send)

    args = parser.parse_args()

    load_dotenv(Path(__file__).with_name(".env"))
    # The SDK reads AGENTMAIL_API_KEY at import time, before .env is loaded, so pass it explicitly.
    api_key = os.environ.get("AGENTMAIL_API_KEY")
    if not api_key:
        print(json.dumps({"error": "AGENTMAIL_API_KEY not set and no .env next to inbox.py"}), file=sys.stderr)
        return 1
    client = AgentMail(api_key=api_key)

    try:
        return args.fn(client, args)
    except ApiError as e:
        print(to_json({"error": "api", "status": e.status_code, "body": e.body}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
