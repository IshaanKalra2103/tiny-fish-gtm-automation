---
name: preview
description: Make one short preview video of a tool doing its job inside this owner's business.
---

# Preview

1. `ws get profile` and `catalog get <tool_id>`.
2. Write one prompt that shows the job happening in THIS business, filmed like a short documentary shot. Use the
   template for the job:
   - missed-calls: "<owner role> on a job <setting>, phone buzzes in a pocket; cut to a phone screen showing a missed
     call answered and a job booked"
   - reviews: "<owner> at the counter of <business> reading a phone, a new review gets a friendly reply, they smile"
   - social-posts: "<business interior>, a phone on a stand photographs today's special; the post appears on screen"
   - booking: "<customer> books an appointment on a phone at night; next morning <owner> sees the day's schedule"
   - website-chat: "<owner> busy with customers in <business>; on a tablet on the counter a chat assistant answers a
     customer's question about hours"
   - books / quotes / marketing-msgs / menu-inventory: the owner finishing the task in seconds on a tablet, in their
     real setting.
   Keep it to one scene, real-looking people and places, warm natural light, no on-screen text beyond a few words, no
   brand logos.
3. `preview make --tool <tool_id> --prompt "<prompt>"`. It returns a cached video if one exists. If the status is
   `capped` or `failed`, tell the owner in one sentence and describe what the tool would do instead.
