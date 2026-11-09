# imessage: MainStreet AI iMessage relay

Owners can text the MainStreet AI agent at the Photon line (+1 415 225 0168). This folder is the relay between that line and the agent API, built on [Photon Spectrum](https://photon.codes/docs/spectrum-ts) (`spectrum-ts`). It carries no model logic.

## What it does

For each incoming text message:

1. `from_hash = sha256(message.sender.id)`. The sender id is the Apple address (phone number or email).
2. `POST ${AGENT_API_URL}/api/imessage` with `{from_hash, text}` and the `X-Relay-Secret: $MS_RELAY_SECRET` header. The call waits up to 300 s, because the API gives a turn up to about 280 s.
3. On 200 `{replies, link}`, it sends each reply (at most 3) 3 s apart, then the link to the owner's page (`/b/o_...`).
4. On 429 it sends the `detail` text, for example "Give me a few seconds between texts."
5. On any other error (401, 5xx, timeout, API down, bad response), it sends "Sorry, something broke on our side. Try again in a minute."

It ignores its own outgoing messages, non-text messages (attachments, reactions and so on) and empty texts. Texts longer than 2000 characters are cut to 2000, the API's limit. A typing indicator shows while the agent works, where Photon supports it.

The logs carry only the first 12 characters of the sender hash, the outcome and the timing. They never contain a phone number, an email or message text.

## Files

- `src/relay.ts`: the handler, `handleMessage(message, {apiUrl, secret, fetch, send, sleep, typing, log})`. It has no Photon dependency, so it can be tested on its own.
- `src/index.ts`: connects to Photon and calls `handleMessage` for each message, each in its own task so that a slow turn never blocks other senders.
- `test/relay.test.ts`: unit tests with a fake `fetch`, `send` and `sleep`.
- `test/api.test.ts`: tests against a real local API running the fake agent. They are skipped unless `RELAY_TEST_API_URL` is set.
- `send_rich.mjs`, `send_image.mjs`, `connect_paperclip.py`: left over from the earlier GTM project, and not used by the relay.

## Run

```sh
npm install
AGENT_API_URL=http://127.0.0.1:8787 MS_RELAY_SECRET=<same as the API> npm start
```

`scripts/live.sh` starts the relay for you, with a fresh secret shared with the API. Only one consumer may read the Photon line. Make sure the old `gtm-paperclip` container is stopped (`docker ps --format '{{.Names}}' | grep -x gtm-paperclip` should print nothing), or both will reply.

## Test

```sh
npm test        # unit tests; the API tests are skipped
npm run typecheck
```

To run the API tests too, start the API with the fake agent from the repo root, then run the tests:

```sh
MS_RUNNER=fake MS_API_PORT=8788 MS_WORKSPACES=/tmp/ms/ws MS_BUDGET_DIR=/tmp/ms/budget MS_RELAY_SECRET=test uv run msapi
cd imessage && RELAY_TEST_API_URL=http://127.0.0.1:8788 RELAY_TEST_SECRET=test npm test
```

## Environment

- `PROJECT_ID`, `PROJECT_SECRET`: the Photon project credentials, kept in `.env`. That file is gitignored; don't print it. Get the values from the [Photon dashboard](https://app.photon.codes).
- `AGENT_API_URL`: the agent API. The default is `http://127.0.0.1:8787`.
- `MS_RELAY_SECRET`: must match the API's `MS_RELAY_SECRET`. If it doesn't, the API answers 401 and owners get the sorry text.
