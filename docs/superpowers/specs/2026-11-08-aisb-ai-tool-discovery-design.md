# MainStreet AI: AI-tool discovery and setup for small businesses (AISB Hack-a-thon, Fall 2026)

Design spec, approved in chat on 2026-11-08. "MainStreet AI" is a working name, set in one config value.

## 1. Goal

Build a prototype platform that helps non-technical Main Street and rural small businesses (restaurants, coffee shops, HVAC, landscaping, salons) **discover, compare and adopt AI tools**. It is the "Angie's List of AI tools" from the AISB brief, with three differences the brief asks for:

- **Discovery:** the platform finds tools itself. A TinyFish pipeline refreshes the catalog weekly.
- **Rating beyond reviews:** each tool gets a visible trust score built from evidence, plus a simulated owner test.
- **Adoption:** an agent sets the chosen tool up for the owner, or the platform points them to a local human helper.

**Deliverables:**
- A link judges can open and test.
- A 10-minute video, due 2026-11-08 at 11:59 PM ET.

The link can keep improving after submission, but the video is final.

## 2. What the judges said (Q&A, 2026-11-05)

- **The product:** a platform that helps a small business find all the AI tools useful to it. It is not one AI tool. It should serve any small business, with Maryland Main Street and rural businesses as the focus.
- **Discovery:** it does not have to be live, but the catalog has to grow. Periodic refreshes are fine.
- **Safety:** don't surface tools from fly-by-night builders, and flag tools whose builder is unknown.
- **Local help:** connect owners with real people who can set tools up for them.
- **The build:** real code, not wireframes. Not everything has to work, as long as what doesn't is labelled.
- **No voice interface** for the platform itself. Voice AI tools can still be listed.
- **The video carries most of the judging.** Most judges only watch it. Padmanabhan and Anand click the links.
- **Defensibility:** be ready to answer why OpenAI or Anthropic couldn't do this overnight.

**Rubric (50 points):**

| Area | Points |
|---|---|
| Depth of research | 10 |
| Small Business Applicability (diverse businesses, legacy software, SBA offerings) | 10 |
| Architecture and Scalability | 10 |
| User Experience | 10 |
| Presentation (contribution from each member) | 10 |

## 3. Owner flow

The same flow runs on the web and over iMessage.

1. **Intake.** The owner either pastes a website or Google Maps link, or types a line such as "2-van HVAC company in Frederick, MD".
   - TinyFish Fetch reads the site.
   - The agent works out the business type, size, location, the software they already use (Square, Toast, Google Business Profile, QuickBooks, Facebook, Instagram, Yelp, Gmail or Outlook) and their likely pains.
   - It shows a "Here's what we understood" card that the owner can edit.
2. **Needs.** The agent lists 3–5 jobs AI could take on, ranked by estimated hours or dollars saved each week. The jobs come from a fixed taxonomy (section 6.2).
3. **Compare.** For each job, 2–3 approved catalog tools appear as cards. Each card shows:
   - the monthly cost (with a free-plan flag) and setup time
   - "works with" chips that match the owner's current software
   - a trust badge with an expandable breakdown
   - the simulated owner-test score, when there is one, labelled "simulated"
   - one plain sentence on what the tool would do for this owner
4. **Preview.** A short AI video (6–8 s) shows the tool at work in this business, for example an AI receptionist booking a call for the owner's HVAC company.
   - Previews are made with OpenRouter video and cached per business and tool.
5. **Adopt.** The owner chooses one of two paths:
   - **"Set it up for me."** The agent shows exactly what it will do (which account, which email, which business details). After the owner approves, it creates an AgentMail inbox, signs up on the vendor site through a TinyFish Agent run, fills in the business details, and stops at any CAPTCHA, phone check or payment step to hand it to the owner. It ends with the login, what was configured, and a short "what's next" list. Progress streams live.
   - **"Find me a local helper."** Shows real organizations with public pages: Maryland SBDC, SCORE and the SBA Baltimore District Office. No named individuals.

## 4. Architecture

```
web (Next.js on Vercel) ──┐                                  ┌─ catalog.json (approved tools)
                          ├─► api (FastAPI on the Mac) ──────┤
iMessage (Photon relay) ──┘    public via Cloudflare tunnel  └─ Docker sandbox, one run per turn:
                               one workspace per owner           claude -p --output-format stream-json
                               streams turn events (SSE)         settings.json  (tool allowlist, deny rules)
                                                                 CLAUDE.md      (role, plain language, safety)
                                                                 skills/*.md    (intake, match, vet, setup-<tool>, preview)
                                                                 owner files    (profile.json, needs.json, ...)
                                                                 tool CLIs: ws, catalog, tf, inbox, preview, approval

catalog pipeline (offline on the Mac, weekly): discover → read → extract → vet → human approve → export catalog.json
```

### 4.1 web/ (Next.js, pnpm, Vercel)

- **Pages:**
  - `/`: intake, with large type and plain words.
  - `/b/[ownerId]`: the business page with profile, needs, comparisons, previews and setups.
  - `/catalog`: browse with filters for business type, job, free plan and "works with".
  - `/tool/[id]`: tool detail with the trust breakdown and sources.
  - `/demo`: the five demo businesses.
- **Data:**
  - The catalog and the five demo businesses ship as static JSON in the build, so browsing and the demos work when the Mac is offline.
  - Live features call `NEXT_PUBLIC_API_URL` (the tunnel). When `/api/health` fails, the site shows a "live agent is offline, explore the demo businesses" banner instead of erroring.
- **Accessibility:** WCAG AA contrast, 18 px base type, everything works by keyboard, and no jargon in the UI copy.

### 4.2 api/ (Python 3.12, uv, FastAPI, on the Mac)

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | API, Docker and Claude auth status |
| `POST /api/owners` `{source: url or text}` | Create an owner workspace and return `owner_id` |
| `POST /api/owners/{id}/turns` `{text, channel: web or imessage}` | Start one agent turn and return `turn_id` |
| `GET /api/turns/{turn_id}/events` | SSE stream of turn events (status lines, file-updated notices, done, error) |
| `GET /api/owners/{id}` | The owner's JSON files (profile, needs, comparisons, previews, setups, approvals) |
| `POST /api/owners/{id}/approvals/{approval_id}` `{decision: approve or reject}` | Record the owner's decision |
| `POST /api/imessage` `{from_hash, text}` | Map a phone hash to an owner, run a turn on `channel=imessage`, return the reply texts |

- **Concurrency:** at most 2 sandboxes run at once (the TinyFish Agent limit). Later turns queue, and each owner's queue position is shown.
- **Logs:** each turn's events are appended to `workspaces/<owner_id>/turns/<turn_id>.jsonl`.

### 4.3 sandbox/ (Docker image plus fixed config)

- **Image:** Node, the Claude Code CLI, uv and Python 3.12, and the tool CLIs. Runs as a non-root user.
- **Each turn runs:**

  ```
  docker run --rm -v workspaces/<owner_id>:/work
    -e CLAUDE_CODE_OAUTH_TOKEN -e CLAUDE_CONFIG_DIR=/work/.claude-config
    -e TINYFISH_API_KEY -e AGENTMAIL_API_KEY -e OPENROUTER_API_KEY
    mainstreet-sandbox claude -p "<turn text>" --resume <session_id>
    --output-format stream-json --model claude-sonnet-5-5
  ```

  The flags restrict the run to the allowlisted tools.
- **Auth:** `claude setup-token` is run once, and the token is stored in the macOS Keychain as service `AISB_CLAUDE_OAUTH`. The API reads it and passes it as an environment variable. It is never written to disk in a workspace.
- **Session continuity:** `session_id` is stored in `/work/session.json`. The Claude config directory lives inside the owner's workspace, so `--resume` works across containers.
- **`settings.json`:** allows only `Bash` calls to the tool CLIs plus `Read` and `Write` under `/work`. Denies `WebFetch`, `WebSearch` and any other command, so all web access goes through `tf`.
- **`CLAUDE.md`:**
  - **Role:** a patient advisor for a non-technical owner.
  - **Language:** plain words.
  - **Channels:** on `imessage`, replies are at most three short texts plus a link to the web page.
  - **Saving results:** every result is saved through `ws save`.
  - **Safety rules:** see section 7.
- **`skills/`:** `intake.md`, `match.md`, `compare.md`, `preview.md`, `setup.md` (the general sign-up procedure, adapted from `agentmail/account-signup/SKILL.md`), and one `setup-<tool-id>.md` playbook per tool the agent can set up.

### 4.4 Tool CLIs (in sandbox/tools, Python via uv)

Each CLI follows Loopcast's contract:
- It prints one JSON line to stdout: `{"ok": true, ...}`, or `{"ok": false, "error": "..."}` with exit code 1.
- Progress goes to stderr.
- It charges a per-owner budget ledger in `/work/budget.json`.

| CLI | Commands | Backed by |
|---|---|---|
| `ws` | `save <kind> <file>` validates the file against the pydantic schema for `profile`, `needs`, `compare`, `preview`, `setup` or `approval`, then writes `/work/<kind>*.json`; `get <kind>` | local files |
| `catalog` | `match --type <business_type> --need <need_id> [--works-with a,b]`, `get <tool_id>` | `catalog.json` (approved tools only) |
| `tf` | `search`, `fetch <urls>`, `agent --url --goal --schema` | TinyFish, reusing `app/src/gtm/tinyfish_tools.py` |
| `inbox` | `create`, `wait --since --match` | AgentMail, reusing `agentmail/inbox.py` |
| `preview` | `make --owner --tool --prompt` | OpenRouter video; returns a cached file if one exists |
| `approval` | `request --summary <text>` writes `approvals/<id>.json` as pending and returns at once. The agent then ends its turn. When the owner decides, the API starts a new turn with the text `Owner <approved or rejected> approval <id>` | local files |

### 4.5 catalog/ (Python, uv, offline pipeline)

1. **Discover.** TinyFish Search runs over a query grid (business type × job × phrasing such as "AI receptionist for HVAC"), plus directories and review sites. Candidates are deduplicated by vendor domain.
2. **Read.** TinyFish Fetch reads each candidate's home, pricing, privacy, about and integrations pages.
3. **Extract.** Headless Claude Code (`claude -p`) turns the pages into a tool record. Pydantic validates it.
4. **Vet.** The pipeline computes the trust signals (section 6.3), each with an evidence URL.
5. **Approve.** A human reviews each tool with `catalog review` (a terminal prompt showing the record and its evidence) and marks it approved or rejected.
6. **Export.** Approved tools are written to `catalog/catalog.json`, which is copied into `web/` and `sandbox/`.

Running it weekly is the growth story. The 16-week version adds TinyFish Monitor on vendor pricing and status pages.

### 4.6 imessage/ (moved from photon/)

- `src/index.ts` loops over `app.messages`. For each text message it POSTs `{from_hash, text}` to `/api/imessage` and sends each returned text with `space.send`.
- `from_hash` is the SHA-256 of the sender address. The raw number is never stored.
- At most 1 message per sender every 5 s, and 30 per sender per day.

## 5. Demo businesses

There are five fictional Maryland businesses, one per type, each with a one-page static site in `demo-sites/<slug>/`. The sites deploy as their own static Vercel project, so they have public URLs before the web app exists:
- a diner (restaurant)
- a coffee shop
- a 2-van HVAC company
- a landscaping crew
- a hair salon

Intake reads their real URLs. Their results and previews are produced ahead of time and shipped as static JSON. Live sign-ups are done only for these fictional businesses, never on behalf of a real business without its owner.

## 6. Data

### 6.1 Tool record (catalog.json, `tools[]`)

```
id, name, vendor, url, need_ids[], business_types[], what_it_does (one plain sentence)
price: {free_plan: bool, from_usd_month: number|null, pricing_url, notes}
setup: {minutes: int, difficulty: easy|medium|hard, agent_setup: bool, playbook: "setup-<id>.md"|null}
integrations: [square, toast, clover, google_business, quickbooks, facebook, instagram, yelp, gmail, outlook, website, sms]
trust: {score: 0-100, badge: verified|caution|unknown, signals: {<name>: {points, max, value, evidence_url}}}
sim_test: {score: 0-10, persona, task, notes, label: "simulated"} | null
sources: [url], status: approved|pending|rejected, reviewed_by, reviewed_at
```

### 6.2 Jobs taxonomy (needs.yaml)

| `id` | Job |
|---|---|
| `missed-calls` | AI phone receptionist |
| `reviews` | Review replies and reputation |
| `social-posts` | Social posts and specials |
| `booking` | Booking and reminders |
| `website-chat` | Website chat and FAQ |
| `books` | Invoicing and bookkeeping |
| `marketing-msgs` | Email and SMS marketing |
| `quotes` | Estimates and quotes, for trades |
| `menu-inventory` | Menu and inventory, for food |

Each business type maps to its default jobs.

### 6.3 Trust score (0–100, every signal shown with evidence)

| Signal | Max | Passes when |
|---|---|---|
| Identity | 25 | A named company, named founders or leaders, and a physical address |
| Longevity | 15 | Domain at least 2 years old, or independent press or funding |
| Data handling | 20 | A privacy policy that says what is collected and whether customer data trains models; SOC 2 or similar counts toward it |
| Pricing transparency | 15 | Public prices, not just "contact us" |
| Independent reviews | 15 | At least 20 reviews on G2, Capterra, the App Store or Google, averaging 4.0 or higher |
| Viability | 10 | Product updates in the last 6 months and no shutdown or acquisition news; Relay.app's September 2026 shutdown is the cautionary example |

**Badges:**
- **Verified:** score of 75 or more, and human approval.
- **Caution:** score of 50–74.
- **Unknown builder:** score under 50, or the identity signal is 0. These tools are hidden by default and show a warning when revealed.

Only Verified tools with `agent_setup: true` can be set up by the agent.

### 6.4 Owner workspace (`workspaces/<owner_id>/`)

```
profile.json, needs.json, compare_<need_id>.json, preview_<tool_id>.json (+ .mp4), setup_<tool_id>.json,
approvals/<id>.json, budget.json, session.json, turns/<turn_id>.jsonl, .claude-config/
```

Setup credentials go in `setup_<tool_id>.json` with file mode 600. The owner sees the password once on their web page. It is never sent over iMessage.

## 7. Safety and budget rules

These are enforced in CLAUDE.md, in the tool CLIs and in the API.

- **Payments:** never enter payment details, and never choose a paid plan.
- **Security checks:** stop at any CAPTCHA, phone verification, "continue in the app" or suspicious-activity screen, and hand that step to the owner. Never try to get around it.
- **Approval:** no account is created until the owner approves the exact summary from `approval request`.
- **What can be set up:** only Verified catalog tools with a playbook.
- **Labels:** simulated scores are always labelled "simulated".

**Budget caps:**

| Scope | Cap |
|---|---|
| Per owner, TinyFish | $1.50 |
| Per setup | $1.00 (about 60 Agent steps) |
| OpenRouter video, all owners | $20 hard cap (`budget/global.json`) |
| Preview clips | 8 s or less; at most 2 live previews per owner and 10 per day overall |

At a cap, the tool refuses and the agent says so in plain words.

## 8. Error handling

- **Tool failures** return `{"ok": false, "error": ...}`. The agent explains the failure in one plain sentence and offers the next best option, such as another tool or a local helper.
- **A TinyFish Agent run that is blocked**, or `COMPLETED` with a failure in `result`, is treated as a handoff to the owner, not a retry. Agent runs are never retried automatically, because a retry can start a duplicate paid run.
- **Docker or Claude failures** end the turn with an `error` event, which the web shows as "Something went wrong on our side, try again". Details go to the turn log.
- **API offline:** the web falls back to the static catalog and the demo businesses.

## 9. Testing

- **pytest, offline:**
  - every tool CLI's JSON contract and exit codes
  - `ws save` schema validation
  - the trust score and badge rules
  - the catalog `match` filters
  - the budget caps
  - the API endpoints, with a fake sandbox runner
- **Live smoke tests**, one of each:
  - an intake-to-compare turn
  - a preview
  - a setup on a demo business
  - an iMessage round trip
- **Web:** `pnpm build` passes, and a Playwright click-through covers intake, needs, compare, preview and setup on a demo business.
- **Previews:** frames are inspected before they are cached. The generated video must match the prompt and show no garbled text.

## 10. Research for the rubric (docs/research.md)

TinyFish Search and Fetch gather sources, and each claim is cited:
- **The market:** US and Maryland small-business counts and employment (SBA Office of Advocacy).
- **AI adoption today:** current AI-adoption rates among small businesses (Census Business Trends and Outlook Survey; US Chamber or similar surveys), and the main barriers (cost, trust, time, know-how).
- **The pains, per business type:** for example, the share of calls trades businesses miss, and how review response affects local search.
- **Existing directories and why they fall short:** G2, Capterra, Product Hunt, "There's An AI For That". They are built for tech buyers, have no setup, and do little vetting.
- **Partners:** Maryland SBDC and SCORE as distribution and helper partners.

## 11. Repo layout and cleanup

1. Commit and push the uncommitted Oct 11–12 Loopcast work on `main` as a snapshot.
2. Create the branch `aisb`.
3. On `aisb`, use this layout:

   ```
   catalog/  sandbox/  api/  web/  demo-sites/  imessage/  docs/  legacy/loopcast/
   ```

4. Move the following into `legacy/loopcast/`, and repoint or remove every reference to the old paths:
   - `app/`, `harness/`, `video/`, `promo/`, `brightdata/`, `identity/`, `deliverables/`, `dist/`
   - `plan.md`, `SHOWDOWN.md`, `CURRENT.md`
5. `legacy/loopcast/` is archived and is not expected to run on this branch. The runnable Loopcast stays on `main`.
6. Reused code moves to its new home rather than being copied:
   - `tinyfish_tools.py` goes to `sandbox/tools`, and the catalog pipeline imports it from there.
   - `agentmail/inbox.py` goes to `sandbox/tools`.
   - `photon/` goes to `imessage/`.
7. The root `README.md` is rewritten for MainStreet AI.

## 12. Tonight's scope vs. the 16-week plan

**Tonight:**
- A catalog of about 40 approved tools across 5 business types and the 9 jobs.
- The 5 demo businesses, run ahead of time, with previews.
- Live intake, needs, compare and preview for any business.
- One live agent setup: an AI website-chat assistant on a free plan, trained on the business's own site. The vendor is chosen by a test sign-up. It must have a free plan, need no card and no phone verification, and accept a website URL as its training source.
- iMessage replies in text only, with a link to the web page.

**16 weeks (for the video):**
- Distribution through Maryland SBDC, the Maryland Department of Labor and SBA partners.
- Real reviews and outcomes from owners, alongside the simulated scores.
- A vetted marketplace of local helpers (students and SBDC advisors).
- Setup playbooks for the top 3 tools in every job.
- Vendor monitoring with TinyFish Monitor, so shutdowns and price changes update the catalog.
- Spanish and other languages.
- Hosted sandboxes, so the agent no longer depends on one Mac.
- Accounts and authentication.

## 13. Risks

| Risk | Mitigation |
|---|---|
| The Mac or tunnel is down when judges test | Static catalog and demos still work. The banner says live features are offline. Keep the Mac awake (`caffeinate`) through Nov 16. |
| A vendor sign-up adds a CAPTCHA or phone check | Hand it to the owner. Keep a recorded successful run for the video, and keep a second vendor ready. |
| Claude Code turns are slow (30–90 s) | Stream status lines. Show the cached demo results first. Use `claude-sonnet-5-5`. |
| Spending runs over | Hard caps in the tool CLIs (section 7), and the global video cap. |
| Not enough time for the video | Code freeze at 7 PM ET, and record from 7 to 10 PM. |

## 14. Timeline (2026-11-08, ET)

| Time | Work |
|---|---|
| 1:00–1:30 | Repo snapshot and restructure; research and catalog discovery start in the background |
| 1:30–4:00 | Sandbox, tools, API and catalog pipeline; vendor test sign-up |
| 2:00–5:30 | Web app (in parallel) |
| 4:00–6:00 | Demo businesses run ahead of time, previews, iMessage relay |
| 6:00–7:00 | End-to-end tests and fixes; code freeze at 7:00 |
| 7:00–10:00 | Record and edit the 10-minute video |
| By 11:30 | Submit the link and video |

The implementation plan assigns team roles, so that each member's part can be shown in the video.
