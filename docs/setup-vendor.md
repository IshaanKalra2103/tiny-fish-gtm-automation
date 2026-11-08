# Vendor choice for "set it up for me" (website chat / FAQ assistant)

Research only, accessed 2026-11-08. No accounts were created and no cloud-browser runs were started; everything below comes from public pages read with TinyFish search and fetch.

## What we need and why

MainStreet AI's agent will later create a free account on a vendor's site using a throwaway inbox and a cloud browser, then configure the tool for a small business. The demo business is fictional: Bean & Brick Coffee, https://mainstreet-demo-sites.vercel.app/coffee/. The vendor has to be one where that is likely to work unattended:

- (a) a free plan, (b) no credit card at signup, (c) no phone verification
- (d) trains from a website URL (crawl) on the free plan
- (e) plain email + password signup (not only Google sign-in)
- (f) an embed snippet or shareable chat link
- (g) a legitimate, established company

Caveat on (c) and bot protection: none of the fetched pages mention phone verification, CAPTCHA, Turnstile, hCaptcha or reCAPTCHA. The signup pages are client-rendered, so the fetched text would not show such widgets anyway. "Not mentioned" below means unverified, not confirmed absent. Only a live test settles it.

## Candidates ruled out

- Chatbase: no free plan any more. Cheapest is Hobby at $40/month with a 7-day trial [S1].
- SiteGPT: "credit card required" for the 7-day trial; no free plan [S2].
- Crisp: free plan exists (website chat widget, 2 seats) but "No AI credits included"; AI needs a paid plan or the 14-day all-features trial [S3].
- Botpress: free plan (100 conversations, 3 AI agents) and a website knowledge base, but it is a bot-builder (Studio), so an unattended setup has many more steps [S4].
- Lindy, Voiceflow, CustomGPT, Elfsight: not fetched; they are not chat-first free-plan products for this use, so they were not pursued.

## Comparison

"Not stated" means the fetched pages say nothing either way.

| Vendor | Free plan limits | Card at signup | Phone verification | URL training on free plan | Email + password signup | Embed / share | Signup URL | Terms URL |
|---|---|---|---|---|---|---|---|---|
| Chatling | $0: 200 AI credits, 1 AI agent, 1 seat, 500,000 knowledge-base characters [S5] | No ("free plan with no credit card required") [S6] | Not stated | Yes; crawler takes a website, sitemap or URL list; free plan lists a knowledge base, and the page-level cap is 1,000 pages [S5][S7][S6] | Yes; form has first name, last name, email, password [S8] | Embed code (copy-paste; documented for WordPress) [S9]; share link not verified | https://app.chatling.ai/register | https://chatling.ai/terms-of-service [S10] |
| Denser.ai | $0: 1 bot, 1 member, 50 queries/month, 100 pages or 50 MB per bot [S11] | No ("No card required") [S11] | Not stated | Yes; website crawl is a free data source [S12][S13] | Yes ("sign up with your email or Google account"; free plan "only requires an email address") [S14][S15] | Embed code to paste into site [S14] | https://denser.ai/ (use "Start free"; direct signup URL not fetchable) | Not found |
| Tidio (Lyro) | $0: 50 billable conversations, 100 Flows visitors; Lyro AI is 50 conversations, one-time [S16] | No ("No credit card required") [S17][S18] | Not stated | Lyro is fed support content, free plan includes the 50 Lyro conversations; website crawl not confirmed on page [S19][S16] | Yes; email, password and website URL [S18] | Widget embed (a standard Tidio snippet; not shown on fetched pages) | https://www.tidio.com/register | https://www.tidio.com/terms/ [S20] |
| Wonderchat | Pricing page: free, 20 credits (about 10 resolutions), 50 webpages, 1 agent, embeddable widget [S21]. Blog and home page say 50 AI replies/month [S22][S23]. Pages disagree. | No ("Not a trial", "No credit card") [S23][S22] | Not stated | Yes; "paste your website or help center address" [S22] | Not confirmed; signup buttons say "Start 7-day Free Trial" on the pricing page [S21] | Embeddable chat widget; "one snippet" [S21][S23] | https://wonderchat.io/ (app at app.wonderchat.io; signup path not fetchable) | https://wonderchat.io/terms-of-service [S24] |
| Botpress | $0: 100 conversations, 3 seats, 3 agents, 100 MB vector storage [S4] | No ("No credit card required") [S25] | Not stated | Yes; knowledge base accepts a website link [S26] | Not confirmed | Embed code in Webchat > Deploy Settings [S27] | https://botpress.com/ (app.botpress.com not fetchable) | https://botpress.com/legal/terms-of-service [S28] |
| Crisp | $0 forever: website chat widget, 2 seats, no AI credits [S3] | Not stated for free | Not stated | No (no AI on free plan) [S3] | Not confirmed | Chatbox embed [S3] | https://app.crisp.chat/initiate/signup/ | https://crisp.chat/en/terms/ [S29] |

## Ranked recommendation

1. Chatling. It is the only candidate where we saw the actual signup form text: first name, last name, email, password, one "Create account" button, plus a terms and privacy line. Free plan, no card, and website crawl are all documented.

   Risks for an automated signup: the first-run flow after signup (onboarding questions, workspace naming) is unseen, and the share-link feature is unconfirmed, so we may only get an embed snippet. A confirmation email or magic link is likely, which the throwaway inbox must handle. Bot protection is unknown. The free tier is small (200 credits), so a single heavy test could use it up. The dashboard route was "app.chatling.ai/register" and the old "/signup" path 404s, so the agent should start from chatling.ai and follow the button rather than hard-code a path.

2. Denser.ai. Free plan with no card, website crawl on the free plan, email signup (Google also offered), and an embed snippet. Plan page is clear and the company is established.

   Risks: signup page could not be fetched, so we do not know the form fields or whether Google is the default and email is hidden behind a link. The free plan allows 50 queries per month and 100 pages, so crawling must be capped to the coffee site's few pages. The terms URL was not found in this pass. Bot protection is unknown.

3. Tidio (Lyro). Large, long-established vendor (it claims 300,000+ companies), and its FAQ says the free account needs email, password and website URL with no card. Terms page fetched.

   Risks: Lyro's AI is only 50 conversations, one time, so after a few tests the assistant stops working on the free plan. Training from a crawl of the URL on the free plan is not confirmed on the page text. The free plan is mainly a live-chat product, and signup forms for large vendors often use CAPTCHA and send a verification email. The Lyro setup flow needs more clicks than Chatling.

Wonderchat is a close fourth: its pricing page and its blog disagree about the free allowance (20 credits vs 50 replies), and its signup buttons are labelled as a 7-day trial, which raises doubt on the no-card claim until seen live.

## Sources (all accessed 2026-11-08)

- S1: https://www.chatbase.co/pricing
- S2: https://sitegpt.ai/pricing
- S3: https://crisp.chat/en/pricing/
- S4: https://botpress.com/pricing
- S5: https://www.chatling.ai/pricing
- S6: https://chatling.ai/ai-chatbot-website
- S7: https://docs.chatling.ai/knowledge-base/data-source-types
- S8: https://app.chatling.ai/register
- S9: https://chatling.ai/docs/integrations/wordpress (from search result snippet)
- S10: https://chatling.ai/terms-of-service
- S11: https://denser.ai/pricing
- S12: https://denser.ai/blog/free-website-chatbot/
- S13: https://denser.ai/
- S14: https://denser.ai/blog/how-to-integrate-ai-in-website/ (from search result snippet)
- S15: https://denser.ai/blog/getting-started-with-denser-ai/ (from search result snippet)
- S16: https://www.tidio.com/pricing/
- S17: https://www.tidio.com/lyro/
- S18: https://www.tidio.com/faq/
- S19: https://www.tidio.com/
- S20: https://www.tidio.com/terms/
- S21: https://wonderchat.io/pricing
- S22: https://wonderchat.io/blog/wonderchat-guide
- S23: https://wonderchat.io/
- S24: https://wonderchat.io/terms-of-service
- S25: https://botpress.com/ (search result snippet: "No credit card required")
- S26: https://botpress.com/blog/how-to-build-your-own-ai-chatbot (from search result snippet)
- S27: https://botpress.com/docs/webchat/get-started/embedding-webchat/ (from search result snippet)
- S28: https://botpress.com/legal/terms-of-service
- S29: https://crisp.chat/en/terms/

## Live test

Not run yet — needs Ishaan's go-ahead (creates a real vendor account for the fictional demo business; about $0.72 per cloud-browser run).
