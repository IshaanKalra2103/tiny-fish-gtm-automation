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
with exit code 1; `wait` exits 2 on timeout; `send` exits 3 when the send budget is spent.

Rate limits: every API call retries 429/5xx up to 5 times, honouring Retry-After (SDK
backoff). `wait` polls every 3 s, backing off to 15 s. `send` is throttled through a shared
ledger (.send-ledger.jsonl next to this file): at least 30 s between sends from one inbox,
at most 40 per inbox and 90 in total per rolling 24 h (free tier: 3,000/month). Each send
carries an Idempotency-Key, so retries never send twice.

The API key comes from AGENTMAIL_API_KEY, else from the .env next to this file.
Inline script metadata keeps uv from using (and re-syncing) any surrounding project venv.
"""

import argparse
import fcntl
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

RETRY = {"max_retries": 5}  # SDK retries 429/408/409/5xx with Retry-After + exponential backoff
LEDGER = Path(__file__).with_name(".send-ledger.jsonl")
SEND_GAP_S = 30
SEND_CAP_INBOX_24H = 40
SEND_CAP_TOTAL_24H = 90
POLL_MAX_S = 15.0

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
        emit(inbox_obj(client.inboxes.create(request=request, request_options=RETRY)))
    return 0


def cmd_list(client, args) -> int:
    for inbox in client.inboxes.list(request_options=RETRY).inboxes:
        emit(inbox_obj(inbox))
    return 0


def cmd_delete(client, args) -> int:
    for inbox_id in args.inbox_ids:
        client.inboxes.delete(inbox_id=inbox_id, request_options=RETRY)
        emit({"deleted": inbox_id})
    return 0


def cmd_messages(client, args) -> int:
    for m in client.inboxes.messages.list(args.inbox, limit=args.limit, request_options=RETRY).messages:
        emit(summary_obj(m))
    return 0


def cmd_read(client, args) -> int:
    emit(full_obj(client.inboxes.messages.get(args.inbox, args.message_id, request_options=RETRY)))
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
    interval = args.interval
    print(f"waiting up to {args.timeout}s for mail to {args.inbox} received after {since.isoformat()}", file=sys.stderr)
    while True:
        # Filter on receipt time client-side: the API orders by the sender's Date header.
        recent = client.inboxes.messages.list(args.inbox, limit=50, include_spam=True, request_options=RETRY).messages
        hits = sorted((m for m in recent if matches(m, args, since)), key=lambda m: m.created_at)
        if hits:
            emit(full_obj(client.inboxes.messages.get(args.inbox, hits[-1].message_id, request_options=RETRY)))
            return 0
        if time.monotonic() >= deadline:
            print(json.dumps({"error": "timeout", "inbox": args.inbox, "since": since.isoformat()}), file=sys.stderr)
            return 2
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
        interval = min(interval * 1.5, POLL_MAX_S)


def reserve_send(inbox: str) -> str | None:
    """Wait out the per-inbox gap and check the 24 h caps, then record the send. Returns an error or None."""
    with open(LEDGER, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # one sender at a time across agents
        f.seek(0)
        cutoff = time.time() - 86400
        recent = [e for e in map(json.loads, filter(str.strip, f)) if e["t"] >= cutoff]
        mine = [e["t"] for e in recent if e["inbox"] == inbox]
        if len(recent) >= SEND_CAP_TOTAL_24H:
            return f"total send budget spent ({SEND_CAP_TOTAL_24H}/24h)"
        if len(mine) >= SEND_CAP_INBOX_24H:
            return f"send budget for {inbox} spent ({SEND_CAP_INBOX_24H}/24h)"
        gap = (max(mine) + SEND_GAP_S - time.time()) if mine else 0
        if gap > 0:
            print(f"throttling: {gap:.0f}s until {inbox} may send again", file=sys.stderr)
            time.sleep(gap)
        f.write(json.dumps({"t": time.time(), "inbox": inbox}) + "\n")
    return None


def cmd_send(client, args) -> int:
    if error := reserve_send(args.inbox):
        print(json.dumps({"error": "send_budget", "detail": error}), file=sys.stderr)
        return 3
    sent = client.inboxes.messages.send(
        args.inbox, to=args.to, subject=args.subject, text=args.text,
        idempotency_key=str(uuid.uuid4()), request_options=RETRY,
    )
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
