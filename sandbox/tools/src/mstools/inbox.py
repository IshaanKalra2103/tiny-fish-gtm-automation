"""inbox: throwaway AgentMail inboxes for sign-ups. create, wait for a verification email, read, list messages.

`wait` and `read` add `codes` (4-8 digit numbers) and `links` found in the mail. The key comes from
AGENTMAIL_API_KEY. Every API call retries 429/5xx up to 5 times, honouring Retry-After.
"""
import argparse
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from .cli import ToolError, log, run

RETRY = {"max_retries": 5}
POLL_MAX_S = 15.0
CODE_RE = re.compile(r"(?<![\d#])\d{4,8}(?!\d)")
LINK_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def client():
    from agentmail import AgentMail

    key = os.environ.get("AGENTMAIL_API_KEY")
    if not key:
        raise ToolError("AGENTMAIL_API_KEY is not set.")
    return AgentMail(api_key=key)


def summary_obj(m) -> dict:
    return {"message_id": m.message_id, "from": m.from_, "subject": m.subject, "preview": m.preview,
            "received_at": m.created_at}


def full_obj(m) -> dict:
    text = m.extracted_text or m.text or ""
    haystack = f"{m.subject or ''}\n{m.text or ''}\n{m.html or ''}"
    return {**summary_obj(m), "to": m.to, "text": text[:4000],
            "codes": list(dict.fromkeys(CODE_RE.findall(f"{m.subject or ''}\n{text}"))),
            "links": list(dict.fromkeys(LINK_RE.findall(haystack)))}


def parse_since(value: str) -> datetime:
    m = re.fullmatch(r"(\d+)([smh])", value)
    if m:
        return datetime.now(timezone.utc) - timedelta(seconds=int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)])
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _wait(c, a) -> dict:
    since = parse_since(a.since)
    deadline = time.monotonic() + a.timeout
    interval = 3.0
    log(f"waiting up to {a.timeout}s for mail to {a.inbox}")
    while True:
        recent = c.inboxes.messages.list(a.inbox, limit=50, include_spam=True, request_options=RETRY).messages
        hits = sorted((m for m in recent if m.created_at >= since
                       and (not a.from_ or a.from_.lower() in (m.from_ or "").lower())
                       and (not a.subject or a.subject.lower() in (m.subject or "").lower())), key=lambda m: m.created_at)
        if hits:
            return {"message": full_obj(c.inboxes.messages.get(a.inbox, hits[-1].message_id, request_options=RETRY))}
        if time.monotonic() >= deadline:
            raise ToolError(f"No email arrived at {a.inbox} within {a.timeout}s.")
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
        interval = min(interval * 1.5, POLL_MAX_S)


def _main(a: argparse.Namespace) -> dict:
    c = client()
    if a.cmd == "create":
        from agentmail.inboxes.types.create_inbox_request import CreateInboxRequest

        req = CreateInboxRequest(username=a.username, display_name=a.display_name, client_id=str(uuid.uuid4()))
        ib = c.inboxes.create(request=req, request_options=RETRY)
        return {"inbox": ib.email or ib.inbox_id}
    if a.cmd == "wait":
        return _wait(c, a)
    if a.cmd == "read":
        return {"message": full_obj(c.inboxes.messages.get(a.inbox, a.message_id, request_options=RETRY))}
    msgs = c.inboxes.messages.list(a.inbox, limit=a.limit, request_options=RETRY).messages
    return {"messages": [summary_obj(m) for m in msgs]}


def main() -> None:
    p = argparse.ArgumentParser(prog="inbox", description="Throwaway email inboxes for sign-ups.")
    sub = p.add_subparsers(dest="cmd", required=True)
    cr = sub.add_parser("create")
    cr.add_argument("-u", "--username")
    cr.add_argument("-n", "--display-name", dest="display_name")
    w = sub.add_parser("wait")
    w.add_argument("inbox")
    w.add_argument("--since", default="5m")
    w.add_argument("--from", dest="from_")
    w.add_argument("--subject")
    w.add_argument("--timeout", type=int, default=240)
    r = sub.add_parser("read")
    r.add_argument("inbox")
    r.add_argument("message_id")
    m = sub.add_parser("messages")
    m.add_argument("inbox")
    m.add_argument("--limit", type=int, default=10)
    run(_main, p)


if __name__ == "__main__":
    main()
