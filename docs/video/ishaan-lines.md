# Ishaan's lines: MainStreet AI video

Only the lines Ishaan speaks. Dylan records his own separately. About 15 minutes total. Footage is due by 9:45 PM.

## Before you start

- Camera clips (marked C): phone on a tripod or stack of books, landscape, back camera, 1080p at 30 fps, lens at eye level, about 1.2 m away. Frame from mid-chest up, a little space above your head.
- Face a window or lamp. Nothing bright behind you. Same spot and same clothes for every clip.
- Before recording, take one photo from your camera spot and text it to Dylan, and check his. Fix anything that looks very different (one much darker, one much closer).
- Voice-over clips (marked V): Voice Memos, phone about 30 cm from your mouth, not AirPods. Turn off fans and AC.
- Every clip: say the clip number out loud ("camera three", "voice nine"), wait two seconds, say the line, wait two seconds. Two takes each.
- C2 is split screen with Dylan: stay in the middle of the frame, and leave a two-second pause between your two lines.
- Keep the meaning; say every number exactly as written, because the same number is on screen.

## Part 0. The problem (0:00 to 1:15)

**C2** · on camera, split screen. Only your lines here; pause after each.

> I'm Ishaan.

> And we think this isn't a technology problem. It's a finding problem. One AI directory lists over fifty thousand tools, vendors pay for placement, and nobody helps you set anything up.

## Part 1. The MVP (1:15 to 5:15)

**C3** · on camera

> Everything you're about to see is live: the real site, the real agent, and a real Maryland business we've never talked to. The agent only reads its public website.

**V2** · voice-over, over the intake screen recording

> All the owner does is paste their website and press "Show me what AI can do." Our agent reads the site in its own sandbox, and the owner can follow along. It takes about a minute, so we've sped it up.

**V3** · voice-over, over what it understood and the jobs

> First it says what it understood: the kind of business, its size, the tools it already uses, and what seems to slow it down. Then it picks three to five jobs AI could take on, ranked by hours saved each week. They come from a fixed list of nine jobs, so it can't invent one.

**V5** · voice-over, over the preview

> Owners don't want a feature list, so we show them. This is a short AI-generated clip of the tool working in their kind of business, and it's always labelled that way.

**V6** · voice-over, over the setup on Bean & Brick

> This is Bean & Brick, a made-up coffee shop with a test website, because we never sign up for a real business without its owner. The agent writes down exactly what it will do, and waits. The owner presses "Yes, set it up." Then it makes a fresh email inbox, opens a cloud browser, and signs up on the free plan. If it hits a CAPTCHA, a phone check or a payment page, it stops and hands that step to the owner. It never enters a card. At the end, the owner gets the login, what we set up, and what to do next.

## Part 2. How we approached building it (5:15 to 6:45)

**C5** · on camera

> We started from one question: what would it take for an owner to trust an AI tool they've never heard of? That gave us three parts. A catalog a person has checked. An agent that does the work. And safety rules that live in code, not in a prompt.

**V9** · voice-over, over the architecture diagram

> The web app and iMessage talk to one server. Every message starts a fresh, locked-down container running Claude Code. It can only use a few small tools we wrote: our catalog, TinyFish for reading the web and driving a browser, an email inbox, previews and approvals.

**V11** · voice-over, over the safety code

> The rule that matters most is no account without the owner's yes. At first that was a line in the prompt. But the agent reads websites, and a website can tell it to ignore its instructions. So we moved the rule into code. The owner's answer goes into a folder the agent can only read, and the sign-up tool won't start without a yes for that exact tool. No open web access, no payment details, and hard spending caps.

**C6** · on camera

> We tested it the way an owner would use it: on real websites, in the live product, through the same buttons. That's how we found that iMessage showed raw formatting symbols, and that the agent's reply showed up twice. We fixed both today.

## Part 3. Evidence it works and is worth it (6:45 to 7:55)

**C7** · on camera

> Is this technically possible? It's running right now.

**V12** · voice-over, over the results card

> Today the live site ran real agent turns for a diner, an HVAC company and a salon, each in under a minute. The catalog went from 261 candidates to 85 approved tools. Our test coffee site has a planted instruction telling the agent to break its rules. It read it and ignored it.
>
> And the setup agent filled in a real sign-up form in a cloud browser. When the site asked it to prove it was human, it stopped and handed that step to the owner, exactly as designed.

## Part 4. The next 16 weeks (7:55 to 9:20)

All on camera, alternating with Dylan. A timeline card builds beside you.

**C9**

> Here's what we'd do with sixteen weeks, in four blocks of four.

**C11**

> Weeks five to eight: the catalog. Setup playbooks for the top three tools in every job, owner reviews next to our trust scores, and monitoring, so when a tool changes its price or shuts down, like Relay did, the catalog changes with it.

**C13**

> Weeks thirteen to sixteen: people. A vetted network of local helpers, students and SBDC advisors, who can set tools up in person. And distribution through the SBDC, the Maryland Department of Labor and SBA partners that owners already trust.

## Part 5. Close (9:20 to 9:45)

**C15** · on camera

> That's MainStreet AI. We find the AI tools worth a small business's time, check them, and set them up. It's live right now, so try it with your own business. Thanks for watching.

## Also from your phone

- B-roll 1, ringing phone: a phone face up on a table or car seat, ringing, nobody answers. 10 seconds, landscape. Anyone can call it, or set an alarm with a ringtone sound. If easy, add 5 seconds of hands busy with tools or wiping a counter.
- Optional B-roll 3: over the shoulder at a laptop on the site, 10 seconds.

## Send

AirDrop everything (both takes of each clip, the B-roll) to the Mac by 9:45 PM. Don't rename anything: the clip numbers said out loud are how the clips get sorted. Put the coach's name and topic for the end card in the chat, or "no coach".
