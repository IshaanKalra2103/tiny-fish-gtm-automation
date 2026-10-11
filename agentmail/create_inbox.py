"""Create AgentMail inboxes for agents.

Usage:
    uv run create_inbox.py                                   # one inbox, random address
    uv run create_inbox.py -u tinyfish-gtm -n "TinyFish GTM" # tinyfish-gtm@agentmail.to
    uv run create_inbox.py -u gtm-agent --count 2            # gtm-agent-1@, gtm-agent-2@
    uv run create_inbox.py --list                            # show existing inboxes
    uv run create_inbox.py --delete a@agentmail.to b@agentmail.to

Reads AGENTMAIL_API_KEY from .env. Each created inbox is printed as one JSON line.
Named inboxes use a deterministic client_id, so re-running the same command
returns the existing inbox instead of creating a duplicate.
"""

import argparse
import json
import os
import sys
import uuid

from agentmail import AgentMail
from agentmail.core.api_error import ApiError
from agentmail.inboxes.types.create_inbox_request import CreateInboxRequest
from dotenv import load_dotenv


def inbox_json(inbox) -> str:
    return json.dumps(
        {
            "inbox_id": inbox.inbox_id,
            "email": inbox.email,
            "display_name": inbox.display_name,
            "created_at": inbox.created_at.isoformat(),
        }
    )


def create(client: AgentMail, username: str | None, display_name: str | None, domain: str | None):
    request = CreateInboxRequest(
        username=username,
        display_name=display_name,
        domain=domain,
        client_id=f"inbox-{username}" if username else str(uuid.uuid4()),
    )
    return client.inboxes.create(request=request)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create AgentMail inboxes for agents.")
    parser.add_argument("-u", "--username", help="local part of the address (random if omitted)")
    parser.add_argument("-n", "--display-name", help='shown as "Display Name <address>"')
    parser.add_argument("-d", "--domain", help="verified custom domain (default agentmail.to)")
    parser.add_argument("-c", "--count", type=int, default=1, help="number of inboxes to create")
    parser.add_argument("--list", action="store_true", help="list existing inboxes and exit")
    parser.add_argument("--delete", nargs="+", metavar="INBOX_ID", help="delete these inboxes and exit")
    args = parser.parse_args()

    load_dotenv()
    # The SDK reads AGENTMAIL_API_KEY at import time, before .env is loaded, so pass it explicitly.
    client = AgentMail(api_key=os.environ["AGENTMAIL_API_KEY"])

    if args.list:
        for inbox in client.inboxes.list().inboxes:
            print(inbox_json(inbox))
        return 0

    if args.delete:
        for inbox_id in args.delete:
            try:
                client.inboxes.delete(inbox_id=inbox_id)
            except ApiError as e:
                print(f"delete {inbox_id} failed ({e.status_code}): {json.dumps(e.body)}", file=sys.stderr)
                return 1
            print(json.dumps({"deleted": inbox_id}))
        return 0

    for i in range(1, args.count + 1):
        username = args.username
        if username and args.count > 1:
            username = f"{username}-{i}"
        try:
            inbox = create(client, username, args.display_name, args.domain)
        except ApiError as e:
            print(f"create failed ({e.status_code}): {json.dumps(e.body)}", file=sys.stderr)
            return 1
        print(inbox_json(inbox))
    return 0


if __name__ == "__main__":
    sys.exit(main())
