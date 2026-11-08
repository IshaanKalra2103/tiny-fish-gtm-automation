# Recommendations

Reviewed October 11, 2026 against the working tree, including uncommitted work. Components were actively changing during this review; this is a snapshot, not a release certification.

**Implementation follow-up:** The subsequent harness consolidation adds a shared brief/stage contract and execution manifest, prerequisite/output enforcement, failed-QA blocking, version-bound approval reconciliation, process locking, atomic JSON writes, container readiness checks, blocked-stage retry, and offline lifecycle tests. See `harness/README.md` for current operation. The findings below describe the earlier review snapshot; budget enforcement, deeper evidence validation, human creative-revision automation, and release packaging still need follow-up.

The next milestone should be **one reproducible campaign that preserves the supplied brief, completes QA, records approval against the exact video, and ships in a runnable package**. The role separation is already useful. The highest-value work is making the boundaries between those roles and the harness agree.

## How the project is structured

| Area | Current responsibility | Assessment |
| --- | --- | --- |
| `app/src/gtm/` | CLI, file-backed campaign state, provider calls, seven pipeline roles, static HTML reports | The main executable product. `cli.py` supports both local orchestration and Paperclip process agents. |
| `harness/` | Dockerized Paperclip, bootstrap, organization configuration, campaign issue creation | Owns task scheduling and human review, but duplicates some workflow decisions made inside the app. |
| `brightdata/` | Separate uv package and CLI for social posts, metrics, and comments | A clear provider boundary with an offline test suite. The app invokes it through a subprocess and shared artifacts. |
| `video/` | Separate uv package for ElevenLabs, images, gameplay, and ffmpeg rendering | Being built independently. The app currently renders through its own MoviePy implementation in `roles/video.py`. |
| `photon/` | Spectrum echo smoke test and native Paperclip channel setup | `src/index.ts` is explicitly a connectivity test; the intended operational integration is `connect_paperclip.py`. |
| `agentmail/` | Standalone uv script for inbox and message operations | Supporting tooling; not a required step in the app's local pipeline. |
| `runs/` | Shared JSON, logs, screenshots, and generated media | Convenient for inspection, but currently doubles as the workflow database without transactional updates. |
| `docs/`, `README.md`, `plan.md`, `CURRENT.md` | Requirements, architecture, onboarding, and build log | Useful context, with several implementation/documentation mismatches. |
| `paperclip/` | Ignored upstream reference checkout | Keep outside this project's application code and test discovery. |

Local execution is `research → analysis → strategy → video → qa → publish → learn`. QA can generate additional scripts and videos itself. The harness instead creates six child issues and attaches QA review plus human approval to the video issue. Those are currently different workflow contracts.

## P0 — Fix the campaign handoffs first

### 1. Make campaign briefs machine-readable end to end

**Evidence:** [`harness/campaign.py`](../harness/campaign.py), `brief_md()`, writes Markdown fields such as `- **Brand / website:** ...`. [`app/src/gtm/cli.py`](../app/src/gtm/cli.py), `_brief_from()`, only parses plain lines such as `brand_url: ...` and `niche: ...`. A brief produced by the harness therefore falls back to the app's TinyFish defaults for these fields.

**Work:** Define one validated campaign brief containing brand name, URL, niche, audience, goal, and platforms. Pass a structured representation through the issue metadata or an explicitly delimited JSON block; generate the human-readable description from it. Reject missing required inputs rather than silently substituting another campaign's target.

**Done when:** A campaign for a different brand and niche reaches `brief.json`, research, script, and report with its inputs preserved. Cover the producer-to-consumer round trip with an offline test.

### 2. Give QA and human approval one authoritative lifecycle

**Evidence:** [`harness/campaign.py`](../harness/campaign.py) attaches review and approval to the video issue. [`app/src/gtm/cli.py`](../app/src/gtm/cli.py), `_paperclip_agent()`, marks a role done after it returns, even when QA's result says `needs_human`. The publish role can then request a separate board approval. [`roles/qa.py`](../app/src/gtm/roles/qa.py) owns its own revision loop, while [`roles/video.py`](../app/src/gtm/roles/video.py), `run()`, always renders version 1.

**Work:** Let the app own draft generation and bounded QA revisions; let Paperclip own scheduling and the human decision. Translate QA outcomes explicitly into review pass, changes requested, or blocked. Make the publishing handoff consume the existing approval for the final version. Inspect actual Paperclip wake payloads before relying on `approval_approved` as the sole signal.

**Done when:** An integration test exercises QA failure, revision, QA pass, human rejection, and human approval. A failed QA result cannot advance as a successful review, a rejection produces a new draft, and only one human gate is required for a given final draft.

### 3. Bind approval to a valid, current artifact

**Evidence:** [`roles/publish.py`](../app/src/gtm/roles/publish.py) changes any existing package to `ready_to_publish` when `approved=True`, including a package marked `needs_human`. It does not recheck QA, video existence, or whether the artifact changed after packaging. Posting is currently simulated, but the state can still misrepresent readiness.

**Work:** Require passing QA and an existing video; store the approved version, artifact hash, actor, timestamp, and decision reference. Invalidate approval after regeneration. If overriding failed QA is intentional, make that a separate recorded decision with a reason.

**Done when:** Failed QA, missing media, stale versions, and changed media cannot become ready through ordinary approval. Repeated approval is idempotent.

## P1 — Make the result trustworthy and repeatable

### 4. Turn the budget into an enforceable execution limit

**Evidence:** [`run.py`](../app/src/gtm/run.py), `charge()`, checks the limit after spend is recorded. [`tinyfish_tools.py`](../app/src/gtm/tinyfish_tools.py) charges Agent after it completes and Browser when it closes. Research catches broad exceptions around those operations, so `BudgetExceeded` can become an ordinary fallback. LLM accounting records tokens at zero dollars; TTS, transcription, and Bright Data spend are not included in that ledger. README advertises a planned $1 cap while config defaults to $1.50.

**Work:** Propagate budget exhaustion as a terminal condition. Check remaining allowance before calls, use provider execution limits where supported, and reserve allowance for concurrent work. Separate provider estimates, actual charges, and unpriced usage. Add a shared deadline: Bright Data's subprocess timeout already equals the harness's entire 900-second role timeout, leaving no guaranteed completion margin.

**Done when:** An exhausted budget prevents new paid work, fallback cannot swallow the stop, and the report clearly shows what costs are measured or unknown.

### 5. Strengthen evidence and QA contracts

**Evidence:** [`roles/qa.py`](../app/src/gtm/roles/qa.py), `_compliance()`, checks whether a claim's URL appears in an allowed set, not whether the source supports the claim. That set includes news search hits which [`roles/research.py`](../app/src/gtm/roles/research.py) does not fetch. An empty claims list passes the citation check. Persona review requirements are matched through free-text prefixes; list lengths and scores have no hard constraints.

**Work:** Store source IDs, retrieval status, and supporting excerpts. Check factual script statements against those excerpts, blocking missing product evidence. Use stable requirement IDs and validate complete review coverage, exactly three personas, score bounds, scene counts, and screenshot indexes. Keep simulated audience scores explicitly labeled.

**Done when:** A real URL with an unsupported claim fails; omitted requirements and invalid structured output fail validation; missing brand evidence produces a clear blocked or degraded outcome.

### 6. Make retries safe and artifacts consistent

**Evidence:** [`run.py`](../app/src/gtm/run.py) writes JSON directly and uses a thread lock that does not coordinate separate processes. [`roles/learn.py`](../app/src/gtm/roles/learn.py) appends duplicate memory entries on rerun. CLI IDs use minute precision. Resuming upstream work does not invalidate downstream scripts, QA, or approval. The Paperclip helper is duplicated in app and harness.

**Work:** Add atomic file replacement, per-run process locking, unique IDs, and a small manifest recording stage status, input hashes, artifact versions, and errors. Upsert learning entries by campaign/version. Define downstream invalidation rules. Choose one source for the Paperclip adapter or enforce copy parity. A database migration is unnecessary until file-level protections prove insufficient.

**Done when:** Retrying a completed stage avoids duplicate work, interrupted writes leave readable state, and changing a brief invalidates dependent outputs and approval.

### 7. Establish a small offline integration suite

**Observed validation:** `uv run --offline --frozen --project brightdata pytest brightdata/tests -q` passed **12 tests**. Those tests use mocked HTTP and cover normalization, snapshots, rate limits, errors, and CLI artifact output. No comparable app/harness suite or repository CI workflow was found in the reviewed files.

**Work:** Add fixtures for the brief handoff, QA/approval transitions, budget stops, retry behavior, and report generation. Add one small renderer check using local assets and fake audio. Run package-scoped tests in CI with uv and frozen lockfiles; isolate live-provider tests behind an explicit command.

**Test-discovery finding:** An initial unscoped pytest invocation from the repository root collected the ignored upstream `paperclip/` tests and failed on Docker/socket prerequisites. The scoped Bright Data suite passed. Configure discovery so local reference clones cannot change this project's test result.

## P1 — Finish the deliverable before expanding scope

### 8. Prove the extracted package works

**Evidence:** [`app/scripts/package.sh`](../app/scripts/package.sh) expects `deliverables/README.md`, `launch-post.md`, and `demo-video.mp4`; these were absent from the reviewed tree. It bundles the captured run under `sample-run/`, but [`config.py`](../app/src/gtm/config.py) and the dashboard default to `runs/`. There is no documented automatic sample replay path. The visible `tinyfish-demo-1` directory contained partial research artifacts when inspected, not a complete run.

**Work:** Finish one live campaign against the chosen target and freeze its artifacts. Add a documented offline replay command, then extract the zip in a clean directory and follow its README. Validate required inputs before packaging and scan the staged output for secrets, including `.env.*` files rather than excluding only `.env`. Record the workflow demonstration and write the launch post from observed results.

**Done when:** The archive contains all four required deliverables, a fresh uv environment can run the app, and the bundled report and media replay without repository-relative dependencies. The recording shows the same target, evidence, revisions, and approval as the saved run.

### 9. Reconcile onboarding with the actual implementation

**Evidence:** Root README still describes Streamlit and TikTok Creative Center; the app serves static HTML and runs its Agent against YouTube. It documents `--brand` as a URL even though the app uses `--brand-url` for that value. Harness documentation places memory at `/workspace/memory/learnings.json`, while app config uses `runs/learnings.json`. Harness stage text expects `analysis.json` and `template_vN.json`, while the app produces `insights.json` containing the template.

**Work:** Publish one current command sequence and artifact contract. Keep historical plans in the work log, and label future functionality separately. Clarify that Photon production routing uses the Paperclip channel and that the echo process should not run alongside it.

**Done when:** Someone unfamiliar with the project can use the documented commands and find each promised artifact without consulting session history.

## P2 — Consolidate after the first reliable run

- **Choose a rendering contract.** Keep the app's working render path for the first verified campaign. Integrate `video/` behind an adapter that returns the transcript, duration, media path, and QA frames the app expects. Before switching, add its system requirements to Docker: `video/` uses ffmpeg/ffprobe, while the reviewed Dockerfile explicitly installs only espeak and fonts for rendering. Avoid maintaining two independent revision pipelines.
- **Improve analysis quality.** `social_posts()` ranks primarily by raw views, and `_memory()` loads the last ten runs without filtering brand or niche. Add freshness, platform-aware comparisons, minimum evidence thresholds, and relevant memory selection before claiming a broadly winning format.
- **Improve review ergonomics.** Extend the static report with explicit failure/degraded states, links to the correct Paperclip review, and version-bound approval information. A new dashboard framework is lower priority than correct state and useful evidence.
- **Keep supporting services optional.** Add channel-specific acceptance tests for campaign creation and approval through Photon once the canonical workflow passes. Expand AgentMail and real publishing only when they serve a verified campaign requirement.

## Suggested work order

1. Fix brief serialization and QA/approval semantics; add focused regression tests.
2. Enforce budget stops and evidence validation; make reruns safe.
3. Complete one live campaign, inspect the video, and freeze a replayable run.
4. Align docs, validate the extracted package, and produce the demo and launch post.
5. Integrate richer rendering, channel controls, and real outcome measurement.

This review inspected local code and documentation and ran the scoped offline tests. It did not start paid provider jobs, exercise live approval APIs, send messages, publish content, or verify a complete live campaign. Findings about cross-service execution should be confirmed with the integration checks above.
