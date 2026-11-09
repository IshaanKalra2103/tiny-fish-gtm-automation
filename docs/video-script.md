# MainStreet AI: 10-minute video script and recording kit

AISB Hack-a-thon, Fall 2026. The video is due 2026-11-08 at 11:59 PM ET. It is final once submitted.

How to use this file:
- Lines in quote blocks (`>`) are spoken. Everything else is direction for the person recording and editing.
- Narration is about 1,150 words, which is about 8:15 at 140 words a minute. The rest of the time is screen action, the ring, the preview clip and sped-up agent waits.
- Every number in the opening is shown on screen with its source, as in `docs/research.md`. Source IDs (S1 to S28) refer to the table at the end of that file.
- Screens are described by route and element, not by tool name, because the catalog is being rebuilt tonight. Product text in quotes (for example "Yes, set it up") is the real button or heading text on the live site as of 7:40 PM.

## Placeholders to fill before recording

Numbers from tonight's catalog run. Each maps to a field printed by `mscatalog stats` (`catalog/src/mscatalog/stats.py`). They appear in the narration (beat 3b) and in `docs/video/catalog-pipeline.html`:

| Placeholder | What it is |
|---|---|
| `{{CANDIDATES}}` | `candidates N`: candidate tools found by discovery |
| `{{VETTED}}` | `vetted N`: tools that got a trust score |
| `{{FAILED_TRUST_PCT}}` | `stats` prints no percent, so compute it: `unknown` from the `badges (vetted)` line divided by `vetted`, times 100, rounded. That is the share scoring under 50 or with no identifiable builder. If you would rather count Caution too, change the narration to "didn't reach Verified". |
| `{{APPROVED}}` | `approved N`: tools a person approved, which is what owners see |
| `{{APPROVED_PER_JOB}}` | The typical approved count in the `tools per job` block (left number). If the jobs are uneven, say "at least N per job" using the smallest, rather than an average. |

Used only in the funnel diagram (set to `""` in the HTML to hide a stage's number if `stats` does not report it):

| Placeholder | What it is |
|---|---|
| `{{READ}}` | `read N`: candidate sites whose pages were read |
| `{{EXTRACTED}}` | `(tools N)` after `extracted`: records that turned out to be real tools |
| `{{SIMTESTED}}` | `sim_test filled: N` |

Team and demo details:

| Placeholder | What it is |
|---|---|
| `[Name A]` | Workstream A, agent core: tool CLIs, sandbox, API (plan Tasks 1, 2, 3, 4, 5, 8, 9) |
| `[Name B]` | Workstream B, catalog and research: discovery pipeline, human review, research doc (Tasks 10, 11) |
| `[Name C]` | Workstream C, web and demos: demo sites, Next.js app, demo bundles (Tasks 6, 12, 13) |
| `[Name D]` | Workstream D, adoption and launch: vendor playbook, iMessage, tunnel and deploy, video (Tasks 7, 14, 15, 16) |
| `[Coach name]`, `[coaching topic]` | Anyone who coached the team. The rules require crediting coaching. If nobody did, delete the line and say so on the credits card. |
| `[Real business name]`, `[Real business URL]`, `[town]` | The real Maryland small business used for live intake in beat 2a. Pick a public website that `tf fetch` can read (not Facebook-only). Intake only reads it; no account is created for a real business. |
| `[Phone owner]` | Whoever holds the test phone in beat 2g |

Diagrams (1920x1080 PNGs, re-render after filling numbers):
- `docs/video/architecture.png`, from `docs/video/architecture.html`
- `docs/video/catalog-pipeline.png`, from `docs/video/catalog-pipeline.html`
- Render command (repo root): `node docs/video/render.mjs docs/video/<name>.html docs/video/<name>.png`

## Product facts the script works around

Checked on https://mainstreet-ai-five.vercel.app at about 7:40 PM with headless Chromium:

1. **Only one demo business is ready.** `/demo` lists five businesses, but only Bean & Brick Coffee (Frederick) has a page; the diner, HVAC, landscaping and salon cards say "Coming soon", and `/b/demo-hvac` is a 404. The opening tells the HVAC story, but the demo is shot on the coffee business and on a live intake. If the HVAC demo lands before recording, add a 5-second cut to `/b/demo-hvac` in beat 2h.
2. **The live agent was offline.** The home page showed "Our live agent is resting right now." Every live beat needs `./scripts/live.sh` running. Each has a cached fallback.
3. **Static demo pages have no approval card.** On `/b/demo-coffee` the "Getting set up" section shows only a finished "Done" record. The approval card ("Ready to set up ...", "Yes, set it up", "Not now") renders only on a live owner page (`/b/o_...`). Beat 2e therefore runs on a live owner created from the Bean & Brick demo site.
4. **Fixture tools are still in the catalog** (5 cards on `/catalog`). Do not read tool names aloud. One fixture tool is `status: pending` yet shows "Verified by our team" and is "Our pick for you" on the coffee page, and its `/tool/...` page opens even though `/catalog` hides it. If the coffee bundle is still on fixtures when you record, stay on the website-chat comparison and do not open that tool.
5. **The tool detail page shows the six-signal breakdown twice** (under the card, and again under "How we scored it"), and the fixture record says "Reviewed by t". For the trust beat, use the "Why this score" expander on a tool card instead, then open one "See the evidence" link.
6. **The second approval says "Already decided"** (not "Already approved"). Inside one card the buttons disable after the first click, so show the duplicate from a second browser tab.
7. **The catalog's business-type filter has no Landscaping option yet** (it lists Coffee shop, HVAC, Restaurant, Salon). Do not film the filter dropdown open unless the real catalog has fixed it.
8. **The simulated-test stage is not in the spec's pipeline** (§4.5 lists discover, read, extract, vet, approve, export). The catalog workstream has since added `simtest.py`, and `stats` prints `sim_test filled`, so the funnel shows it as step 5. If that count is 0 tonight, set `{{SIMTESTED}}` to `""` and drop "simulated test" from both diagrams.

---

## The script

### Beat 1. The missed call and the numbers (0:00 to 1:15)

**1a. 0:00 to 0:13: cold open**

> That's Dave's phone. Dave runs a two-van heating and cooling company in Hagerstown, and right now he's under a furnace. Dave is made up. The missed call isn't.

- Show: a phone face-up on a workbench or truck seat, ringing, "Incoming call" on screen; cut to hands working inside a furnace or AC panel. 8 to 12 seconds, staged by a teammate, phone ring as the only sound for the first 2 seconds.
- Fallback: black screen with the ring sound, then plain white text centered: "Dave can't pick up."

**1b. 0:13 to 0:55: the numbers**

> Invoca, a call-tracking company, found that 27 percent of calls to home-services businesses go unanswered.
>
> AI can answer the phone today. So why isn't Dave using it? Census data says only about one in five U.S. businesses used AI in the past two weeks. Of owners not planning to, most said it doesn't apply to them, and 22 percent said they don't know what it can do.
>
> That's not a technology problem. It's a finding problem. One AI directory lists over fifty thousand tools, vendors pay for placement, and nobody helps you set anything up.

- Show: one full-screen card per number, large figure centered, one plain line under it, and the source under that (centered, not in a corner):
  - "27%" / "of calls to home-services businesses go unanswered" / "Invoca, May 2024. Vendor data. [S8]"
  - "19.8%" / "of U.S. businesses used AI in the past two weeks" / "U.S. Census Bureau, BTOS, May 2026 [S4]"
  - "65%" and "22%" side by side / "of firms not planning to use AI: 'not applicable' and 'don't know what AI can do'" / "Census CES Working Paper 26-25, Nov 2025 to Jan 2026 [S7]"
  - "50,000+" / "AI tools listed on There's An AI For That; makers pay for placement" / "theresanaiforthat.com/about, 2026 [S19]"
- Fallback: none needed (static cards).

**1c. 0:55 to 1:15: what we built**

> So we built MainStreet AI, for Maryland's 697,000 small businesses first. Think Angie's List, but for AI tools. It reads your business, finds the jobs AI can take off your plate, compares tools we've actually checked, and if you say yes, sets one up for you.

- Show: a number card "696,710" / "small businesses in Maryland, 99.6% of all Maryland businesses" / "SBA Office of Advocacy, 2025 Maryland profile [S2]" for the first sentence, then the home page `/` top, the headline "Find the AI tools worth your time, and let us set them up.", slow scroll to the four "How it works" steps.
- Fallback: same page with the agent offline; crop out the yellow banner.

### Beat 2. Product demo (1:15 to 6:15)

**2a. 1:15 to 1:50: intake of a real business (live)**

> Let's try a real business. This is [Real business name], in [town]. All the owner has to do is paste their website and hit "Show me what AI can do."
>
> Our agent reads the site in its own sandbox, and you can follow along as it works. It takes a minute or two, so we've sped this part up.

- Show: `/`, paste `[Real business URL]` into the big text box, click "Show me what AI can do". The browser lands on `/b/o_...`; the "Working on it" progress card fills with status lines. Speed up the wait 4 to 8x in the edit.
- Fallback: `/b/demo-coffee` (cached run). Change the line to "This is Bean & Brick, one of our example businesses, a coffee shop in Frederick," and cut the progress card.

**2b. 1:50 to 2:25: what we understood, and the jobs**

> First it tells the owner what it understood: what kind of business, how big, which tools they already use, and what seems to slow them down. If it got something wrong, they can fix it.
>
> Then it picks three to five jobs AI could take on, ranked by hours saved each week. These come from a fixed list of nine jobs, so the agent can't make up a category.

- Show: the "Here's what we understood" card (type and town, size, "Tools you already use" chips, "What seems to slow you down"). Scroll to "Jobs AI can take off your plate": numbered jobs, each with "About N hours saved each week".
- Fallback: the same two sections on `/b/demo-coffee`.

**2c. 2:25 to 3:20: compare, with the trust breakdown**

> For each job we show two or three tools side by side: price, free plan or not, setup time, and which of your current tools it works with.
>
> Every tool has a trust score out of 100. Open it and you see six checks: who's behind it, how long it's been around, how it handles your data, public prices, independent reviews, and whether it'll be around next year. Each point links to its evidence.
>
> Seventy-five or more, plus a person's sign-off, makes a tool Verified. Tools from unknown builders stay hidden unless you ask. That matters: Relay.app, an automation tool, shut down this summer and deleted its customers' workflows.

- Show: a "Tools for: <job>" row of cards: "Our pick for you", price or "Free plan", "Works with" chips, the badge and score. Click "Why this score" on one card to open the six rows with points and "See the evidence". Open one evidence link in a new tab for 2 seconds. Then `/catalog`, tick "Show unvetted tools" so the "Careful: tools marked 'Unknown builder'..." warning appears. During the Relay line, a card: "Relay.app shut down. Free users lost access Aug 15, 2026; paid users Sept 14. All workflows deleted." / "TechCrunch, Aug 17, 2026 [S21]; relay.app [S22]".
- Fallback: the same cards on `/b/demo-coffee` (website-chat row only, see product fact 4).

**2d. 3:20 to 3:40: the preview**

> Owners don't want to read a feature list, so we show them. This is a six-second AI-generated preview of the tool working in this business. It's always labelled as AI-generated.

- Show: "See it in your business"; play the clip full length with sound off, then hold on the caption "AI-generated preview of how ... would work in your business".
- Fallback: the cached preview on `/b/demo-coffee` (6 s clip of a barista and a tablet chat).

**2e. 3:40 to 5:00: the agent sets it up, with approval and handoff (live)**

> Now the part no directory does: setting it up. For this we use Bean & Brick, a made-up coffee shop with a test website. We never sign up for a real business without its owner.
>
> I ask it to set up the website chat. First it writes down exactly what it will do, which site, which plan, which details, and waits. Nothing happens until the owner says yes.
>
> Now it makes a fresh email inbox, opens a cloud browser, signs up on the free plan and fills in the business details. You can watch it live.
>
> If it hits a CAPTCHA, a phone check or a payment page, it stops and hands that step to the owner. It never enters a card.
>
> At the end the owner gets the login, what we set up, and what to do next. If they approve twice, from the phone and the laptop, it says "already decided." No second sign-up.

- Show, in order, on a live owner page created from the Bean & Brick demo site:
  1. "Ask us anything" chat box; click the "Set it up for me" suggestion.
  2. The approval card "Ready to set up ..." with the exact summary and the buttons "Yes, set it up" and "Not now". Hold 3 seconds on the summary text.
  3. Click "Yes, set it up"; "Thank you. We are on it." appears.
  4. The setup record status "Setting it up now"; click "Watch live" to show the cloud browser filling the sign-up form. Speed up.
  5. Either "We need you for one step" with the handoff reason, or "Done" with "Log in at", "Username", "What we set up", "What is next for you", and "Show password once". Blur the password in the edit.
  6. A second tab on the same page: click "Yes, set it up"; it shows "Already decided".
- Fallback: the recorded setup run from Task 13 Step 4, plus the "Done" record under "Getting set up" on `/b/demo-coffee`. If no recording exists, cut steps 2 to 4 and 6, and change the narration to "Here's a finished setup from earlier tonight."

**2f. 5:00 to 5:15: a local helper instead**

> Some owners would rather have a person. Every business page has "Find me a local helper": the Maryland SBDC, SCORE, and the SBA's Baltimore office. Real organizations, and often free.

- Show: the "Find me a local helper" card with its three links; hover the Maryland SBDC link.
- Fallback: the same card on `/b/demo-coffee`.

**2g. 5:15 to 5:50: iMessage (live, on a phone)**

> Most owners live on their phones, not laptops. So the same agent works over iMessage. [Phone owner] texts: I run a hair salon in Westminster. A few short, plain replies come back, with a link, and the link opens the same business on the web.

- Show: phone screen recording (or the phone filmed from above): the text "I run a hair salon in Westminster MD, what AI could help me?" sent to the Photon line, 1 to 3 replies arriving a few seconds apart, then a tap on the `/b/o_...` link opening the business page in mobile Safari.
- Fallback: a phone screen recording of the same round trip made earlier tonight. If iMessage (Task 14) is not working, cut this beat, give its 35 seconds to beat 2c, change the first line of beat 3a to "The web app talks to one server.", and drop the iMessage box from `docs/video/architecture.html`.

**2h. 5:50 to 6:15: it still works when the agent is down**

> Right now the agent runs on one Mac, so we planned for it going down. The site says so plainly, and owners can still browse the catalog and our example businesses, which are saved runs of the real agent.

- Show: run `./scripts/live.sh stop` (or just reload a tab after stopping it), reload `/`: the yellow banner "Our live agent is resting right now. You can still explore five example businesses and the full tool catalog." Click "See an example business": `/demo`, then the coffee card, then `/catalog`.
- Fallback: this beat is itself the fallback; it needs no live agent. Restart `./scripts/live.sh` right after.

### Beat 3. How we built it (6:15 to 7:45)

**3a. 6:15 to 6:40: architecture**

> Here's how it's built. The web app and iMessage talk to one server. Every message starts a fresh, locked-down container running Claude Code. It can only run six small tools we wrote, for saving results, our catalog, TinyFish web access, email, previews and approvals. It saves checked files, and the web page shows them.

- Show: `docs/video/architecture.png`, full screen. Optional slow push-in on the sandbox box.
- Fallback: none needed (static image).

**3b. 6:40 to 7:05: the catalog pipeline, with tonight's numbers**

> The catalog comes from a separate pipeline. Tonight it found {{CANDIDATES}} candidate tools, read their websites, and scored {{VETTED}} of them on the six trust checks. {{FAILED_TRUST_PCT}} percent failed. Then a person reviewed each one, and {{APPROVED}} made it in, about {{APPROVED_PER_JOB}} per job. It reruns weekly, so the catalog grows.

- Show: `docs/video/catalog-pipeline.png` with the numbers filled in. Optionally 3 seconds of the terminal running `catalog review` (one tool record and its evidence on screen) before the funnel.
- Fallback: if the numbers are not in by recording time, record this beat last, or say "hundreds of candidate tools" and show the funnel without numbers (set every count to `""`).

**3c. 7:05 to 7:45: the sandbox and the safety rules**

> The rule that matters most: no account without the owner's yes. At first it was a line in the prompt. But the agent reads websites, and a website can say "ignore your instructions." Our test coffee site has one on purpose. So we moved the rule into code. Our server writes the owner's decision into a folder the agent can only read; the operating system blocks writes. The sign-up tool won't start without a yes for that exact tool. Plus: no open web access, no payment details ever, and hard spending caps.

- Show: `sandbox/settings.json` in an editor (allow list of the six tools; deny list with `WebFetch`, `WebSearch`, `curl` and the protected files), then a terminal inside the sandbox image: `touch /decisions/x` returning "Read-only file system" (verified in the Task 9 ledger). Then the "Safety rules" section of `sandbox/CLAUDE.md`.
- Fallback: `docs/video/architecture.png` zoomed on the yellow "/decisions ... mounted read-only" bar.
- Do not say the injection test passed unless the Task 8 smoke test confirmed it.

### Beat 4. The 16-week plan (7:45 to 9:00)

> Tonight is a prototype. Here's what sixteen weeks looks like.
>
> First, distribution. Owners already trust the Maryland SBDC, the Maryland Department of Labor and SBA partners, so we'd reach owners through them, not through ads.
>
> Second, real reviews and outcomes from owners, next to the simulated scores, so the trust score learns from real use.
>
> Third, a vetted marketplace of local helpers, students and SBDC advisors, who can set tools up in person.
>
> Fourth, setup playbooks for the top three tools in every job. Tonight we have one.
>
> Fifth, vendor monitoring with TinyFish Monitor, so when a tool changes its price or shuts down, like Relay did, the catalog updates.
>
> And Spanish and other languages, plus hosted sandboxes and real accounts, so the agent no longer depends on one Mac.

- Show: a plain list card that builds one line at a time, matching spec §12: "Distribution through Maryland SBDC, Maryland Department of Labor and SBA partners" / "Real owner reviews and outcomes, next to simulated scores" / "Vetted local helpers: students and SBDC advisors" / "Setup playbooks for the top 3 tools in every job" / "Vendor monitoring: price changes and shutdowns update the catalog" / "Spanish and other languages" / "Hosted sandboxes, accounts and sign-in". Same fonts and colors as the diagrams (cream background, dark green).
- Fallback: none needed.

### Beat 5. Why OpenAI or Anthropic can't do this overnight (9:00 to 9:30)

> Why couldn't OpenAI or Anthropic build this overnight? They could build the chat. The chat isn't the hard part. The hard part is a catalog a person has checked against evidence, every week. Maryland partners that owners already trust. Actually setting the tool up. And being accountable, through the SBDC and the university, to owners in our own state.

- Show: four short lines on one card, appearing with the narration: "Checked by a person, with evidence, every week" / "Maryland partners owners already trust" / "We set it up" / "Accountable through the SBDC and the university".
- Fallback: none needed.

### Beat 6. Who built what (9:30 to 10:00)

> [Name A] built the agent core: the tools, the sandbox and the server. [Name B] built the catalog pipeline and did the research. [Name C] built the web app and the example businesses. [Name D] built the setup playbook, iMessage and the launch, and put this video together. Thanks to [Coach name] for coaching us on [coaching topic]. Thanks for watching.

- Show: credits card, one row per workstream: "[Name A]: agent core, tool CLIs, sandbox, API" / "[Name B]: catalog pipeline, human review, research" / "[Name C]: web app, demo businesses" / "[Name D]: setup playbook, iMessage, deploy, video" / "Coaching: [Coach name], [coaching topic]" / the judges' link `https://mainstreet-ai-five.vercel.app`.
- Better, if time allows: each member says their own sentence on camera or in voice-over (the Presentation score asks for each member's contribution).
- Fallback: none needed.

---

## Shot list

| # | Time | Shot | Source | Live? | Fallback |
|---|---|---|---|---|---|
| 1 | 0:00 | Ringing phone, hands in a furnace or AC panel | Staged phone footage | No | Black card, ring sound, "Dave can't pick up." |
| 2 | 0:13 | Four number cards with sources (S8, S4, S7, S19) | Title cards made in the editor | No | None needed |
| 3 | 0:55 | Maryland number card (S2), then home page headline and "How it works" | Title card, then `/` | No | Same page; crop out the offline banner |
| 4 | 1:15 | Paste a real URL, click "Show me what AI can do", progress card | `/` then `/b/o_...` | Yes | `/b/demo-coffee` |
| 5 | 1:50 | "Here's what we understood" card and "Jobs AI can take off your plate" | `/b/o_...` | Yes | `/b/demo-coffee` |
| 6 | 2:25 | "Tools for: ..." cards, "Why this score" open, one evidence link | `/b/o_...` | Yes | `/b/demo-coffee`, website-chat row |
| 7 | 2:50 | "Show unvetted tools" warning | `/catalog` | No | Same |
| 8 | 3:10 | Relay.app shutdown card (S21, S22) | Title card | No | None needed |
| 9 | 3:20 | Preview plays, caption visible | `/b/o_...` "See it in your business" | Yes | `/b/demo-coffee` preview |
| 10 | 3:40 | "Set it up for me", approval card, "Yes, set it up" | Live owner page from the Bean & Brick demo site | Yes | Recorded setup run (Task 13 Step 4) |
| 11 | 4:10 | "Setting it up now", "Watch live" cloud browser | Same, plus the TinyFish stream tab | Yes | Recorded setup run |
| 12 | 4:30 | Handoff ("We need you for one step") or "Done" record, password blurred | Same | Yes | "Getting set up" on `/b/demo-coffee` |
| 13 | 4:50 | Second tab, "Already decided" | Same page, second tab | Yes | Cut |
| 14 | 5:00 | "Find me a local helper" card | Any business page | No | `/b/demo-coffee` |
| 15 | 5:15 | iMessage round trip, tap the link | Test phone | Yes | Earlier phone recording; else cut |
| 16 | 5:50 | Offline banner, `/demo`, coffee page, `/catalog` | `/`, `/demo`, `/b/demo-coffee`, `/catalog` with the agent stopped | No | Is the fallback |
| 17 | 6:15 | Architecture diagram | `docs/video/architecture.png` | No | None needed |
| 18 | 6:40 | Optional `catalog review` terminal, then the funnel | Terminal; `docs/video/catalog-pipeline.png` | No | Funnel without numbers |
| 19 | 7:05 | `settings.json`, `touch /decisions/x` refused, CLAUDE.md safety rules | Editor and terminal | No | Architecture diagram, zoomed on `/decisions` |
| 20 | 7:45 | 16-week plan list card | Title card | No | None needed |
| 21 | 9:00 | "Why not OpenAI or Anthropic" card | Title card | No | None needed |
| 22 | 9:30 | Credits card with workstreams, coaching and the link | Title card | No | None needed |

## Recording checklist

Set up the screen:
- [ ] Display at 1920x1080 (on a Retina Mac, record a 1920x1080 region or set the display to "looks like 1920x1080").
- [ ] Browser zoom at 125%. At that zoom the page is laid out like a 1536x864 window, which is how the screenshots behind this script were taken.
- [ ] A clean browser window: no bookmarks bar, no extensions, no other tabs, light mode.
- [ ] Do Not Disturb on, Slack and Mail closed, dock hidden, desktop clear.
- [ ] Cursor highlight on (optional), mouse moves slow.

Get the live agent running:
- [ ] `./scripts/live.sh` printed the production URL, the tunnel URL and `health ok`.
- [ ] Reload `/`: the yellow "Our live agent is resting right now" banner is gone.
- [ ] The catalog run is exported and deployed, so `/catalog` shows the real tools, not the 5 fixtures.
- [ ] Do one practice intake before recording (each owner has a $1.50 TinyFish cap and 2 live previews; use a fresh owner for the take).
- [ ] Create the live Bean & Brick owner for beat 2e ahead of time (paste the coffee demo site URL from `https://mainstreet-demo-sites.vercel.app`), run it up to the compare, and keep that tab open.

Get the phone ready:
- [ ] The test phone is charged, on Do Not Disturb except Messages, screen recording added to Control Center.
- [ ] The Photon line (+1 415 225 0168) is saved as a contact, and the relay (`imessage`, `npm start`) is running.
- [ ] Send one practice text and check the reply and the link before the take. Remember the 1 message per 5 s and 30 per day limit per sender.

Have every fallback in place before you start:
- [ ] `/b/demo-coffee` open in its own tab (fallback for beats 2a to 2d, 2e's "Done" record, and 2f).
- [ ] The recorded setup run from Task 13 Step 4 (fallback for beat 2e).
- [ ] An earlier phone recording of the iMessage round trip (fallback for beat 2g).
- [ ] Both diagram PNGs re-rendered after filling the numbers, and opened once at full size to check them.

Fill the placeholders:
- [ ] `{{CANDIDATES}}`, `{{VETTED}}`, `{{FAILED_TRUST_PCT}}`, `{{APPROVED}}`, `{{APPROVED_PER_JOB}}` in beat 3b and in `docs/video/catalog-pipeline.html`; `{{READ}}`, `{{EXTRACTED}}`, `{{SIMTESTED}}` in the HTML (or `""`).
- [ ] `[Name A]` to `[Name D]`, `[Coach name]`, `[coaching topic]`, `[Real business name]`, `[Real business URL]`, `[town]`, `[Phone owner]`.
- [ ] Search this file for `{{` and `[Name` before recording the narration.

Record and edit:
- [ ] Record the narration separately, in a quiet room, one mic, about 140 words a minute.
- [ ] Speed up agent waits (intake, setup) 4 to 8x, and say on screen "sped up".
- [ ] Every number in the opening has its source line on screen.
- [ ] No corner labels or watermark text on the screen recordings.
- [ ] Blur the setup password and any real email address.
- [ ] Final length 10:00 or less. Export 1920x1080, H.264, and watch it once end to end before submitting.
