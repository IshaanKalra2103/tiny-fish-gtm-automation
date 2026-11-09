# Recording brief: what Ishaan and Dylan record

The video is due at 11:59 PM tonight. To leave time for the cut, render and upload, send footage by **9:45 PM**. Recording everything takes about 25 minutes.

A = Ishaan. B = Dylan.

## The film (9:45 total)

The four parts the rubric asks for each get a title card, so judges can check them off.

| Time | Part | On screen | Voice |
|---|---|---|---|
| 0:00 to 1:15 | The problem | Ringing phone, number cards, split screen of you both | B, then A |
| 1:15 to 5:15 | 1. The MVP: proof of concept | Live site screen recordings, iMessage on a phone | A and B voice-over, 2 short camera bridges |
| 5:15 to 6:45 | 2. How we approached building it | Architecture and catalog diagrams, code | A and B |
| 6:45 to 7:55 | 3. Evidence it works and is worth it | Results cards from tonight's real runs | A and B |
| 7:55 to 9:20 | 4. The next 16 weeks | You two on camera, a timeline card building beside you | A and B alternate |
| 9:20 to 9:45 | Close | Ishaan, then the end card | A |

About 3.5 minutes of this is you on camera. The rest is voice-over on screen recordings, which I capture myself.

## How to record

Camera (on-camera clips, marked C):
- A phone on a tripod or a stack of books, landscape, back camera, 4K or 1080p at 30 fps.
- Lens at eye level, about 1.2 m away. Frame from mid-chest up, with a little space above the head.
- Face a window or lamp. Never put a window behind you.
- Same spot and same clothes for every clip, so I can cut between them.
- Record 1080p, not 4K: smaller files upload faster and the film is 1080p anyway.

Recording apart (you are not in the same place):
- Each of you records only your own lines, on your own phone, whenever suits you. Nobody needs to be on a call.
- Match each other so the cuts look like one film. Both stand (or both sit), lens at eye level, about 1.2 m away, light from a window in front, a plain wall or a tidy room behind, no strong colored light.
- Sit or stand in the middle of the frame with space on both sides. The split-screen opener (C2) keeps the middle half of each frame, so your head and shoulders must fit there.
- Before recording, each of you takes one photo from your camera spot and texts it to the other. Fix anything that looks very different (one much darker, one much closer). It takes a minute.
- Split-screen dialogue (C2): say your own lines only, with a two-second pause between them, looking into the lens. I time the back-and-forth in the edit.

Voice-over (clips marked V):
- Record in the same quiet room with Voice Memos, phone about 30 cm from your mouth. Not AirPods: their mic sounds thin.
- Dylan: record your V lines as landscape video like the rest; I take the sound from them. For those clips move the phone to arm's length (framing doesn't matter, the picture is not used), so the voice sounds close, not roomy.
- Turn off fans and AC. Soft furnishings help; a bare kitchen echoes.

Every clip:
1. Say the clip number out loud ("camera four" or "voice nine").
2. Wait two seconds. Look into the lens (C clips).
3. Say the line. Wait two seconds before you stop.
4. Do two takes. Send both.

You don't need the exact words. Keep the meaning, and say every number exactly as written: the same number is on screen.

## Part 0. The problem (0:00 to 1:15)

**C1 (B, single)**, over the ringing-phone B-roll:
> Dave runs a two-van heating and cooling company in Hagerstown. Right now he's under a furnace, and his phone is ringing. Dave is made up. The missed call isn't.

**V1 (B)**, over the number cards:
> Invoca, a call-tracking company, found that 27 percent of calls to home-services businesses go unanswered. AI can answer the phone today. So why isn't Dave using it? Census data says only about one in five U.S. businesses used AI in the past two weeks. And of the firms not planning to, 22 percent said they don't know what AI can do.

**C2 (split screen: A records the A lines, B records the B lines)**:
> A: I'm Ishaan.
> B: And I'm Dylan. We're Team Forge.
> A: And we think this isn't a technology problem. It's a finding problem. One AI directory lists over fifty thousand tools, vendors pay for placement, and nobody helps you set anything up.
> B: So we built MainStreet AI. Think Angie's List, but for AI tools. It reads your business, finds the jobs AI can take off your plate, compares tools we've actually checked, and if you say yes, it sets one up for you.

## Part 1. The MVP (1:15 to 5:15)

**C3 (A, single)**:
> Everything you're about to see is live: the real site, the real agent, and a real Maryland business we've never talked to. The agent only reads its public website.

**V2 (A)**, intake:
> All the owner does is paste their website and press "Show me what AI can do." Our agent reads the site in its own sandbox, and the owner can follow along. It takes about a minute, so we've sped it up.

**V3 (A)**, what it understood and the jobs:
> First it says what it understood: the kind of business, its size, the tools it already uses, and what seems to slow it down. Then it picks three to five jobs AI could take on, ranked by hours saved each week. They come from a fixed list of nine jobs, so it can't invent one.

**V4 (B)**, the comparison and the trust score:
> For each job we compare up to three tools: price, free plan, setup time, and which of your current tools they work with. Every tool has a trust score out of 100, from six checks: who's behind it, how long it's been around, how it handles your data, public prices, independent reviews, and whether it'll be around next year. Every point links to its evidence. This matters. Relay.app, an automation tool, shut down this summer and deleted its customers' workflows.

**V5 (A)**, the preview:
> Owners don't want a feature list, so we show them. This is a short AI-generated clip of the tool working in their kind of business, and it's always labelled that way.

**C4 (B, single)**, bridge:
> Every directory stops at a list. We go one step further and set the tool up. But never without the owner's yes.

**V6 (A)**, the setup:
> This is Bean & Brick, a made-up coffee shop with a test website, because we never sign up for a real business without its owner. The agent writes down exactly what it will do, and waits. The owner presses "Yes, set it up." Then it makes a fresh email inbox, opens a cloud browser, and signs up on the free plan. If it hits a CAPTCHA, a phone check or a payment page, it stops and hands that step to the owner. It never enters a card. At the end, the owner gets the login, what we set up, and what to do next.

**V7 (B)**, a local helper:
> Some owners would rather talk to a person. Every page links the Maryland SBDC, SCORE and the SBA's Baltimore office. Real organizations, and often free.

**V8 (B)**, iMessage (goes with B-roll 2):
> Most owners live on their phones, so the same agent works over iMessage. I text it like I'd text a friend. A few short, plain replies come back, and the link opens the same business on the web.

## Part 2. How we approached building it (5:15 to 6:45)

**C5 (A, single)**:
> We started from one question: what would it take for an owner to trust an AI tool they've never heard of? That gave us three parts. A catalog a person has checked. An agent that does the work. And safety rules that live in code, not in a prompt.

**V9 (A)**, architecture:
> The web app and iMessage talk to one server. Every message starts a fresh, locked-down container running Claude Code. It can only use a few small tools we wrote: our catalog, TinyFish for reading the web and driving a browser, an email inbox, previews and approvals.

**V10 (B)**, the catalog pipeline:
> The catalog is its own pipeline. Today it found 261 candidate tools, read their websites, and scored 109 real tools on the six trust checks. Then a person reviewed every one. 85 made it in, and 24 didn't. That leaves at least two approved tools for every job in every business type we cover.

**V11 (A)**, safety:
> The rule that matters most is no account without the owner's yes. At first that was a line in the prompt. But the agent reads websites, and a website can tell it to ignore its instructions. So we moved the rule into code. The owner's answer goes into a folder the agent can only read, and the sign-up tool won't start without a yes for that exact tool. No open web access, no payment details, and hard spending caps.

**C6 (A, single)**:
> We tested it the way an owner would use it: on real websites, in the live product, through the same buttons. That's how we found that iMessage showed raw formatting symbols, and that the agent's reply showed up twice. We fixed both today.

## Part 3. Evidence it works and is worth it (6:45 to 7:55)

**C7 (A, single)**:
> Is this technically possible? It's running right now.

**V12 (A)**, over a results card:
> Today the live site ran real agent turns for a diner, an HVAC company and a salon, each in under a minute. The catalog went from 261 candidates to 85 approved tools. Our test coffee site has a planted instruction telling the agent to break its rules. It read it and ignored it.
>
> And the setup agent filled in a real sign-up form in a cloud browser. When the site asked it to prove it was human, it stopped and handed that step to the owner, exactly as designed.

**V13 (B)**, value:
> Is it worth it? More than a quarter of home-services calls go unanswered, and each one can be a lost job. For the salon, our agent estimated that online booking alone would save about four hours a week. And owners who don't use AI told the Census they don't know what it can do. Finding, checking and setting up is exactly the gap we fill.

Only if true: if either of you has talked to a real owner about this, add **C8 (either, single)**: one or two sentences on what they said. Don't invent one.

## Part 4. The next 16 weeks (7:55 to 9:20)

All on camera, singles, alternating. A timeline card builds beside you.

**C9 (A)**:
> Here's what we'd do with sixteen weeks, in four blocks of four.

**C10 (B)**:
> Weeks one to four: real owners. We'd run twenty Maryland businesses through it with the SBDC and measure one thing: is the tool we set up still in use a month later?

**C11 (A)**:
> Weeks five to eight: the catalog. Setup playbooks for the top three tools in every job, owner reviews next to our trust scores, and monitoring, so when a tool changes its price or shuts down, like Relay did, the catalog changes with it.

**C12 (B)**:
> Weeks nine to twelve: scale. Hosted sandboxes and sign-in, so it serves thousands of owners at once, and Spanish and other languages.

**C13 (A)**:
> Weeks thirteen to sixteen: people. A vetted network of local helpers, students and SBDC advisors, who can set tools up in person. And distribution through the SBDC, the Maryland Department of Labor and SBA partners that owners already trust.

**C14 (B)**:
> Why couldn't a big AI company do this overnight? They could build the chat. The hard part is a catalog a person checks against evidence every week, partners owners already trust, and actually setting the tool up.

## Part 5. Close (9:20 to 9:45)

**C15 (A, single)**:
> That's MainStreet AI. We find the AI tools worth a small business's time, check them, and set them up. It's live right now, so try it with your own business. Thanks for watching.

Then the end card: "MainStreet AI", "Team Forge", the site link https://mainstreet-ai-five.vercel.app, and the coaching credit if there is one (the rules ask for it).

## B-roll (phone, 10 minutes)

1. **Ringing phone.** A phone face up on a table or car seat, ringing, nobody answers. Ishaan records it; anyone can call the phone (or set an alarm with a ringtone sound). 10 seconds, landscape. If easy, add 5 seconds of hands busy with tools or wiping a counter.
2. **iMessage, as an iPhone screen recording** (B's phone). Text the MainStreet line, +1 415 225 0168: "I run a hair salon in Westminster MD, what AI could help me?" Keep recording until the replies arrive (about a minute), then tap the link and let the page load. The relay is running on the Mac now.
3. **Optional.** Over the shoulder of both of you at a laptop on the site, 10 seconds.

## What I make myself

- Screen recordings of the live site: intake on a real Maryland business, the jobs, the comparison and trust breakdown, the preview, the approval and setup on Bean & Brick, the local helpers, the catalog.
- Title cards, number cards with sources, the results card, the 16-week timeline, the architecture and catalog diagrams, and the credits.
- The cut in fframes: your clips, voice-over, screen recordings and cards, with captions.

## Send me

1. Ishaan: AirDrop your files to the Mac (they land in Downloads). Dylan: upload yours to a Google Drive or iCloud folder and text Ishaan the link; he puts the files in `footage/` in the repo. Nobody renames anything: the clip numbers you said out loud are how I sort them.
2. In the chat: the coach's name and topic for the end card, or "no coach".
