# Scotive — market research pack

**Date:** 14 September 2026  
**Purpose:** One document covering what people actually said, what Scotive does (including cadence + pause + pay link), who pays, how to rank, and how to talk so Scotive is not another QBO/Xero.  
**Rule used:** No invented demand. Quotes are verbatim from public threads and pages collected in research. Ahrefs numbers are from the keyword exports you ran. Keywords Explorer via MCP had **0 API units** (trial reset 10 Oct 2026); Domain Rating came from Ahrefs’ free DR endpoint.

**Product source of truth:** [scotive.com](http://scotive.com/), `/integrations`, `/guides`, plus your stated live flow (Gmail/Outlook + optional QBO/Xero, thread matched to invoice, Follow-up draft). Cadence that pauses on replies/promises + pay link in the draft is treated as **shipped**.

---

## 0. Verdict in one page

| Question | Answer |
|---|---|
| Is the pain real? | Yes. People write about it constantly on Reddit, LinkedIn, Indie Hackers, Stack Exchange, QuickBooks Community. |
| Does Scotive match the highest-pay pain? | **Yes on the chase job** (awkward follow-up, forgotten nudges, dumb accounting reminders, promises, “says paid,” pay path). **No** on deposits, collections, legal, or “I’m broke this week.” |
| Strength on matching complaints (with cadence) | **~8/10** for agencies/consultants with a pile of open invoices. |
| Will that ICP swipe a card? | **Yes** at **$29–$49/month** if they have **8+ open invoices**. **No** if they have one late invoice (they want a free template). |
| Goal $3k–$10k MRR | **60 customers × $49 ≈ $3k. 200 × $49 ≈ $10k.** Possible, not easy. LinkedIn is how you get the 60. SEO (6 KD 0–5 pages) is slow at DR 0. |
| Positioning | QBO/Xero **create and track the invoice**. Scotive **sits on top**: matches Gmail/Outlook to that invoice, runs an approved Friendly cadence, **pauses** when the client replies or promises, puts a **pay link** in the draft. Not a new books app. |

**One line:** QuickBooks and Xero remind a due date. Scotive reminds a conversation.

---

## 1. What Scotive is (including the one change)

### 1.1 Flow you already had

1. Sign up.  
2. Connect **Gmail or Outlook**.  
3. Optionally connect invoicing/accounting (**QBO, Xero**, and others).  
4. Scotive fetches invoices.  
5. It pulls the email conversations that belong to those invoices and **matches thread → invoice**.  
6. It sets a **state** (unpaid, overdue, promised, broken promise, dispute, partial, says-paid, paid, needs reply, etc.).  
7. User sees statuses and clicks **Follow-up**.  
8. Scotive drafts the next email from **the client’s own language**, so the owner is not guessing.

Nothing Firm/Final has to auto-send. Approval-first was already the trust feature.

### 1.2 The one change (now in the product)

**Approved cadence that pauses on replies and broken promises, plus a pay link in the draft.**

**Approved cadence** = the user approves the *rules* once (or per client), not every Friendly email.

Typical ladder (from how people already chase):

- Before due: short heads-up  
- Due / 1–3 days late: Friendly reminder (can send on the clock)  
- ~7 days: another Friendly  
- After that: **Firm / Final still need a click** (research: a bot after ~7 days overdue starts to hurt the relationship)

Sends from the user’s Gmail/Outlook, same thread, same invoice match.

**Pause** = the matching you already do becomes a brake:

- Client **replied** → hold. No “just checking in” on an open conversation.  
- **Promised** (“paying Friday”) → hold until that date, then **needs you** (broken promise), not another generic reminder.  
- **Dispute / says paid / partial / needs your reply** → hold. Human Follow-up.  
- **Paid** (accounting sync or confirm) → cadence dies. Never chase someone who paid.

**Pay link** = existing QBO/Stripe/PayPal/bank pay URL inside every draft. Scotive is not a payments company.

That change is what made the #1 stated want (“a system sends so it isn’t me nagging”) line up with the unique job (“don’t be as dumb as QBO when they already talked”).

---

## 2. Why they still need Scotive if they have QBO / Xero reminders

Those products already send payment reminders. People still chase by hand. Research reason:

| QBO / Xero / FreshBooks know | They do not know |
|---|---|
| Amount, due date, paid or not | The Gmail/Outlook thread |
| A calendar (“7 days overdue”) | “Paying Friday,” a dispute, “we already paid,” a missing PO |
| A canned template from the accounting domain | The client’s words, from the owner’s inbox |

Native reminders **do not pause** when the client replies. They send reminder 2 on top of an open conversation. Xero **caps** reminders (~5) then goes silent. QBO reminders **fail to send** or cannot be turned off (Intuit Community). Xero mail from `xero.com` gets ignored or spam-filtered.

**Scotive sits on top of the stack they already pay for.** They keep QBO/Xero as the ledger. Scotive is the chase layer on email + that ledger.

If someone has two invoices, never gets replies, and QBO reminders actually fire — they do not need Scotive. The buyer is the person who **already has QBO/Xero and is still in Gmail writing “just checking in.”**

---

## 3. What people complained about — word for word

Grouped the way we scored the product. Each quote is from a public URL.

### 3.1 Tight match — this is the product

#### Awkward chase / hate writing the nudge

> “one of the most stressful parts of the job is dealing with late invoices and chasing for money. I always feel awkward following up…. it’s like I’m walking a fine line between being…”  
> — [r/smallbusiness, Late invoices are killing me](https://www.reddit.com/r/smallbusiness/comments/1i5ag3r/late_invoices_are_killing_me/)

> “I'd wait weeks to send a reminder because I didn't want to be annoying.”  
> — [r/smallbusiness, Honestly realizing I'm the reason my clients pay me late](https://www.reddit.com/r/smallbusiness/comments/1qwxo35/honestly_realizing_im_the_reason_my_clients_pay/)

> “the worst part isn't sending the invoice, it's chasing it afterwards.”  
> “That awkward ‘just checking in on this invoice’ email.”  
> Electrician user: chasing “makes him feel like he's being desperate, which he hates.”  
> — [Indie Hackers, PayNudger](https://www.indiehackers.com/post/chasing-overdue-invoices-is-awkward-i-built-a-small-tool-to-automate-reminders-4f89bae266)

> “Sending those ‘just following up’ emails is easily the most stressful, time-consuming, and awkward part of running an independent business.”  
> — [Alain Ghamachi, LinkedIn](https://www.linkedin.com/posts/alain-ghamachi-4084b321_freelancelife-solopreneur-businesssystems-activity-7466149109666811904-jWIZ)

**Scotive:** context draft in the client’s language + cadence so they don’t postpone the send.

#### Want a system so it doesn’t feel like *me* nagging

> “When it's ‘the system sends a reminder at day 7,’ nobody takes it personally.”  
> — [r/smallbusiness, How do you handle clients who keep delaying payment?](https://www.reddit.com/r/smallbusiness/comments/1tw05u4/how_do_you_handle_clients_who_keep_delaying/)

> “don't rely on memory. set a fixed cadence: reminder at 7 days late, firmer email at 14, call at 21, work pause at 30.”  
> “The part that matters most is having one clear next-follow-up date for every unpaid invoice.”  
> — [r/smallbusiness, How do you actually handle chasing overdue invoices?](https://www.reddit.com/r/smallbusiness/comments/1tmi375/how_do_you_actually_handle_chasing_overdue/)

> “We probably spend 30% of our time chasing down money. … We also use an online invoice system that has automatic payment reminder emails. This has actually worked better than I expected. It is also a nice middle man to blame. Instead of me personally harassing clients I can blame the ‘automated messages in the system’.”  
> — [Freelancing Stack Exchange](https://freelancing.stackexchange.com/questions/9687/chasing-debts-during-coronavirus-lockdown-uk)

> “If you run a small agency, freelance, or bookkeeping practice, you've felt this: you send an invoice, wait 2 weeks, chase by email… It's the most repetitive 4–5 hours of the week.”  
> — [r/nocode](https://www.reddit.com/r/nocode/comments/1u87oub/i_automated_my_clients_invoice_followup_workflow/)

LinkedIn (Nick Saraev): late invoices were money already earned sitting at net 30 turning into net 60; he built a 7 / 14 / 21 autopilot. Comment on that post: automate until ~7 days overdue, then a human message — a polite bot after that “actually hurts.”  
— [Nick Saraev, LinkedIn](https://www.linkedin.com/posts/nick-saraev_how-i-collect-every-overdue-invoice-on-autopilot-activity-7473381537619599360-tnRG)

**Scotive:** approved Friendly cadence = “the system.” Firm/Final still a click.

#### Inbox archaeology / no next action

> “And before you know it, you're scrolling through a spreadsheet trying to remember who owes what, checking old emails, and sending another ‘just checking in’ message.”  
> — [Zainab Oladokun, LinkedIn](https://www.linkedin.com/posts/zainab-oladokun12_automation-n8n-operationspartner-activity-7493332756257513472-VI6N)

Scotive homepage pain copy (product, not a third-party quote): “Scrolling months of sent mail to reconstruct who owes what — every single week.”

**Scotive:** invoice fetch + thread match + ledger.

#### Promises, “says paid,” replies — accounting reminders go blind

> “I'd also track ‘client said they paid’ separately from ‘payment received.’ Those are not the same status, and mixing them up causes a lot of the back-and-forth.”  
> — [r/smallbusiness, chasing overdue invoices](https://www.reddit.com/r/smallbusiness/comments/1tmi375/how_do_you_actually_handle_chasing_overdue/)

> “despite multiple promises to pay, they never did.” Invoices under $600, 90 days overdue.  
> — [r/RealEstatePhotography](https://www.reddit.com/r/RealEstatePhotography/comments/133edqm/anyone_used_debt_collection_agencies/)

Zainab’s n8n flow (same LinkedIn post): if the client replied recently, promised to pay, asked a question, or already addressed the invoice, **the workflow holds**. “No unnecessary ‘just following up’ email.” AI writes a **Gmail draft** for a human.

Indie Hackers comment: split paths — not due yet, admin lag, waiting on pay run, no owner, **disputed scope**. “A generic ‘just checking in’ reminder is fine at first, but after that the useful question is usually: which process is this invoice stuck in.”  
— [PayNudger thread](https://www.indiehackers.com/post/chasing-overdue-invoices-is-awkward-i-built-a-small-tool-to-automate-reminders-4f89bae266)

**Scotive:** states from the thread; cadence **pauses** on reply / promise / dispute / says-paid.

#### QBO / Xero reminders are not enough

> “Automatic Invoice reminders are not being sent. The Automatic Invoice Reminders setting is on and has always been on. … I recommend everyone check your invoice history and make sure those reminders are actually going out. If not, you're paying for a service that isn't being delivered.”  
> — [QuickBooks Community](https://quickbooks.intuit.com/learn-support/en-us/reports-and-accounting/automatic-invoice-reminders-not-sending/00/1447597)

> “Upon checking, there's an ongoing investigation (INV-97602) regarding the automatic sending of invoice reminders in QuickBooks Online (QBO).”  
> — [QuickBooks Community, INV-97602](https://quickbooks.intuit.com/learn-support/en-us/reports-and-accounting/issue-with-automatically-sending-invoice-reminders/00/1394534)

Xero users, quoted on competitor write-ups of the product-ideas forum:

> “Does Xero not think we care about getting paid once we've sent 5 reminders? Change to unlimited until paid.”

> “More than 80% of our invoices are paid late and sometimes we have to send up to 10 reminders over the course of 3–4 months. So, 5 automatic invoice reminders aren't getting the job done.”  
> — collected on [Unpaid: Xero reminder limits](https://www.getunpaid.io/blog/xero-invoice-reminders-limitations-alternatives)

Trove: Xero emails from `xero.com` more likely spam-filtered and ignored; “People respond to people.”  
— [Trove, Xero 5-reminder cap](https://trove.works/xero-reminder-cap/)

**Scotive:** chase from the owner’s Gmail/Outlook; not a third cap of noreply@ accounting mail.

#### Pay link in the reminder

Every public template cluster people search (Stripe, invoice-generator, “polite invoice reminder email”) includes invoice #, amount, due date, **and a payment link**. Knockly, PaidZen, InvoiceSherpa sell this as the point of the email.

**Scotive:** pay link in the draft (their existing link).

---

### 3.2 Partial match — second priority

Ghosting / ignored / then a phone call / pause work — cadence helps; it does not replace calling AP or stopping work.

> “$1,400. 34 days overdue. Invoice opened 6 times (I can see it). Zero replies.”  
> — [r/Freelancers](https://www.reddit.com/r/Freelancers/comments/1ucm9bq/a_client_owes_me_1400_and_has_somehow_forgotten/)

Agency 30 days past due: “Stop emailing. Call AP directly.” “If I don’t have payment or a confirmed payment date by [date], I’ll move this to collections.”  
— [r/agency](https://www.reddit.com/r/agency/comments/1rx30hg/how_to_get_big_client_to_pay_my_last_invoice_that/)

Steve Folland LinkedIn: mix of FreeAgent automatic reminders, then a phone call.  
— [LinkedIn](https://www.linkedin.com/posts/stevefolland_freelancers-how-do-you-chase-an-unpaid-activity-7437040855099568128-9KVl)

**Scotive:** Friendly cadence + Firm as a click. Not phone AI, not collections.

---

### 3.3 Does not match — do not sell these

**Cash-flow emergency**

> “I am a new, small freelancer currently owed $8000 … they haven't paid me a penny in 3 months… My credit card is maxed and I have no money to pay it's bill. My bank account has $60 in it, money left over that was borrowed from a family member to pay last month's rent.”  
> — [r/povertyfinance](https://www.reddit.com/r/povertyfinance/comments/1ji64cs/nonprofit_not_paying_my_invoices/)

They need money this week, not a $49 SaaS.

**VA / collections as the substitute**

> “Was drowning in admin work. Invoice follow-ups… Hired a VA from the Philippines. $7/hour, 20 hours/week. $560/month. … Chased 23 overdue invoices. Collected $4,200 I would've eventually written off.”  
> — [r/SaaS](https://www.reddit.com/r/SaaS/comments/1pek3qf/hired_a_va_for_7hour_roi_was_11x_in_month_one/)

Collections: agencies take **~30%** of recovered.  
— [r/freelance](https://www.reddit.com/r/freelance/comments/48ebi9/psa_forget_about_suing_clients_send_it_to/)

**Process, not software:** deposits, milestones, Net 7 instead of “due upon receipt,” pause work. Loud on Reddit. Scotive does not fix contract terms.

**Freelancers who won’t subscribe**

> “freelancers are famously cheap for anything recurring — I'd probe whether they'd pay monthly at all, or only when they have an invoice outstanding.”  
> “If the answer is one [late invoice], they want words; if it's eight, they want your product.”  
> — [Indie Hackers](https://www.indiehackers.com/post/validating-a-saas-idea-for-freelancers-automated-follow-ups-for-unpaid-invoices-8828912910)

FollowDue: **$19 one-time** templates you paste into Gmail — the freelancer alternative to any subscription.

---

## 4. How accurately Scotive matches (with cadence)

| Complaint cluster | Match | Why |
|---|---|---|
| Awkward nudge / blank reply box | Tight | Draft in their language |
| Postpone follow-up for weeks | Tight | Cadence sends Friendly on a clock |
| “Blame the system” | Tight | Approved ladder |
| Who owes what / sent-mail archaeology | Tight | Invoice + thread ledger |
| Promised Friday / broken promise | Tight | State + pause until date |
| Client already replied | Tight | Pause |
| Says-paid vs received | Tight | Separate states; cadence must not fire |
| Dispute / partial | Tight | Pause; human Follow-up |
| QBO/Xero reminders dumb, capped, broken | Tight | Chase from Gmail/Outlook |
| Reminder with no way to pay | Tight | Pay link in draft |
| Ghosting after many emails | Partial | Email helps; research wants a call / pause work / collections |
| Bookkeeper volume AR | Partial | Cadence helps; Firm-every-click still friction |
| Cash-flow crisis | No | Out of scope |
| Collections / small claims / legal | No | Out of scope |
| Deposits / milestones / pause work | No | Contract, not the product |
| Create invoices / books / taxes | No | They already have QBO/Xero |
| Late fees, SMS, credit checks, phone AI | No | Chaser / Paidnice — not a micro-SaaS |

**Do not market “we solve late payments.”** Market: **inconsistent, context-blind chasing on invoices they already sent.**

---

## 5. ICP who will actually use and pay

### 5.1 Goal math

Indie target stated in research: **$3k–$10k/month**.  
At **$49/month**: **60 customers ≈ $2.9k MRR; 200 ≈ $9.8k.**  
That is 60–200 operators, not a mass freelancer audience.

Observed prices (public sites, 14 Sep 2026): Knockly **$29**; InvoiceSherpa Sole Proprietor **$49**; Paidnice from **$69**; Chaser Compact **$259 / £199**; VA in the Reddit post **$560/month**. Ads: **$8 CPC** on `invoice reminder software`, **$6–$7** on QuickBooks reminder queries.

### 5.2 Who pays (sell only to these)

| ICP | Use Scotive? | Swipe the card? | How you know |
|---|---|---|---|
| **Agency / studio ops or founder**, ~8–40 people, B2B retainers, Gmail or Outlook + QBO | Yes — pile of open invoices | **Yes.** One recovered invoice covers a year. Cheaper than Chaser or a VA. | r/agency 30-day past due; LinkedIn agency cadence posts |
| **Consultant / fractional** with 8+ open invoices, email as system of record | Yes | **Yes at $29–$49** | IH split: eight late invoices want a scheduler |
| Bookkeeper chasing AR for several clients | Yes if cadence is on | **Maybe** | They may still want full auto-send like Paidnice |

**LinkedIn titles:** Agency Owner, Managing Director, Head of Operations, Studio Manager, Principal Consultant.  
**Filter:** people who mention retainers / unpaid invoices / QBO / Xero.  
**Walk away:** Chaser already works; Xero reminders already enough.

### 5.3 Who feels pain but will not pay (do not target)

| Who | Why not |
|---|---|
| Solo freelancer, 1–3 late invoices | Want a $0 template or $19 one-time pack |
| Cash-flow emergency posters | Need money now |
| Finance / credit-control teams | Buy Chaser, Upflow, Gaviti (DR 68–70) |

### 5.4 Ease of hitting $3–10k

**Product–pain fit is no longer the blocker.**  
**Medium-hard** because you must (1) only talk to 8+ open-invoice operators, (2) do LinkedIn every week, (3) wait on DR 0 SEO.

If ~1 in 20 targeted conversations becomes a $49 sub, you need hundreds of conversations. Known indie path. Not a fantasy. Not “easy.”

---

## 6. How to market so you are not QBO, Xero, or “invoice software”

### 6.1 Never say

- Invoice software, invoicing app, create invoices, free invoice generator  
- QuickBooks alternative, Xero alternative, replace your books  
- Accounts receivable automation (900 SV, KD 6 — **Chaser/Upflow buyer**, sister term CPC **$35**)  
- “Anyone who bills” as the ICP on the homepage  

Ahrefs tagged many keywords **Category: Invoicing**. That is their taxonomy. **Page copy must still say chase layer.**

### 6.2 Always say

**You already invoiced them. Scotive watches the thread and the open invoice, and handles the next chase.**

Phrases that match complaints and do not sound like a books app:

- “QBO knows it’s overdue. It does not know they promised Friday.”  
- “We match the Gmail/Outlook thread to that invoice so you don’t send ‘just checking in’ on an open reply.”  
- “Reminders pause when they talk back. Accounting reminders don’t.”  
- “The next email is in their words, from your address. You approve Firm/Final.”  
- “Not a new books app. You keep QBO/Xero. We run the chase.”  

**Reusable line:** QuickBooks and Xero remind a due date. Scotive reminds a conversation.

### 6.3 Stack picture (use in sales and on the software page)

```
Client work
    → QBO / Xero / Zoho / FreshBooks     (create invoice, due date, paid/unpaid, books)
    → Gmail / Outlook                    (the actual conversation)
    → Scotive                            (match thread to invoice, state, cadence, pause, pay link, drafts)
```

Existing tools = **invoicing + ledger**.  
Scotive = **chase on top of that ledger and that inbox.**

### 6.4 LinkedIn (primary customer channel)

- Titles in 5.2 only. Not “Freelancer.”  
- Post the **broken-promise** job, not “AI invoice chasing.”  
- Outreach question: “How do you track a promised payment date vs an overdue invoice?” Memory/spreadsheet = in-market.  
- Proof in week one: forgotten invoice or broken promise surfaced.

### 6.5 Public price

Print **$29–$49/month**. Homepage research fetch had no paid plan, only “free to start.” Peers who convert print the number. Charge when there are more than a handful of open invoices (the one-vs-eight fork).

---

## 7. Programmatic SEO (Ahrefs you ran)

**Facts:** scotive.com **DR 0**. Chaser 68, Upflow 70, Paidnice 56, InvoiceSherpa 40. Other chase clones ~0.  
Keyword Explorer MCP: **0 units**. Numbers below are **your** Keywords Explorer exports (US).

People search **reminder / follow-up / past due email**, not “invoice chasing” (term cluster: reminder 250, software 260, chasing 10). State sentences (“I’ll pay Friday”) are **not indexed** — they are H2s, not 50 URLs.

**Do not target:** `accounts receivable automation` (900 SV, KD 6), `ar automation software` (500 SV, KD 19, CPC $35).

### 7.1 Six URLs — that is the whole cluster (~1.2k of ~1.3k relevant US SV, KD 0–5)

Ship order: **2 → 1 → 3 → 4 → 5 → 6**.

#### Page 1 — `/invoice-reminder-software` (commercial)

| Keyword | SV | KD | CPC | Role |
|---|---|---|---|---|
| **invoice reminder software** | 100 | **0** | **$8.00** | Primary. Parent: payment reminder software |
| **payment reminder software** | 150 | **0** | — | Same page |
| **automated invoice reminders** | 150 | N/A | $0.45 | Same page (cadence story) |
| invoice chasing software | 10 | — | — | Supporting only |
| automated invoice follow up | 20 | — | — | Supporting |

**On-page story:** You already have QBO/Xero. Approved cadence, pause on reply/promise, pay link, from Gmail/Outlook.

#### Page 2 — `/past-due-invoice-reminder` (highest TP — ship first)

| Keyword | SV | KD | TP | Role |
|---|---|---|---|---|
| **past due invoice reminder** | 150 | **1** | **700** | Primary. Parent: overdue invoice email |
| overdue invoice reminder email | 100 | 2 | 500 | Same page |
| past due invoice email | 150 | 0 | 200 | Same page |

**H2s (unindexed complaints):** I’ll pay Friday / promised and didn’t / says paid / partial / after they replied.  
**Do not** make a separate URL for `late payment notice` (parent = **90 days past due letter** — collections letter). Short section on this page only.

#### Page 3 — `/payment-reminder-email-template`

| Keyword | SV | KD | Role |
|---|---|---|---|
| payment reminder email template | 150 | 4 | Primary |
| outstanding payment reminder | 60 | 5 | Same (GSV 250) |
| unpaid invoice reminder | 40 | 4 | Supporting (TP 700 — related cluster) |

Softer / pre-due templates. Overdue ladder stays on page 2.

#### Page 4 — `/how-to-chase-outstanding-invoices`

| Keyword | SV | KD | GSV | TP | Role |
|---|---|---|---|---|---|
| **how to chase outstanding invoices** | 30 | **0** | **300** | **0** | Primary. Right ICP sentence. TP 0 = no extra cluster. |
| invoice follow up email | 30 | 0 | 200 | 20 | Same page. Parent *is* how to chase outstanding invoices |

Write for conversion and UK/AU (GSV 300), not for a traffic spike.

#### Page 5 — `/quickbooks-invoice-reminders`

| Keyword | SV | KD | CPC |
|---|---|---|---|
| quickbooks invoice reminders | 40 | 0 | $6 |
| quickbooks automatic invoice reminders | 20 | 0 | $7 |

Branded. Intuit on the SERP. Angle: QBO reminds a due date; it does not read the thread.

#### Page 6 — `/xero-invoice-reminders`

| Keyword | SV | GSV |
|---|---|---|
| xero invoice reminders | 40 | 200 |

Only if Xero is live. Same angle as page 5 (cap, spam, not from their inbox).

### 7.2 Keyword pass order (for writers)

**P1:** past due invoice reminder → invoice reminder software → payment reminder software → automated invoice reminders → overdue invoice reminder email → past due invoice email  

**P2:** payment reminder email template → outstanding payment reminder → how to chase outstanding invoices → invoice follow up email  

**P3:** quickbooks invoice reminders → quickbooks automatic invoice reminders → xero invoice reminders  

Every template page ends with: cadence runs Friendly, **pauses on reply/promise**, pay link in the draft, keep QBO/Xero.

---

## 8. Competitors (context only — do not become them)

| Product | Public price (fetched) | Who they sell to | Auto-send? |
|---|---|---|---|
| Chaser | Compact **$259/mo** / **£199** | Finance / credit control, revenue bands | Yes |
| Upflow | Quote; GIV bands | B2B finance teams | Yes (~85% emails automated, their site) |
| InvoiceSherpa | **$49** Sole Proprietor | Agencies, law, IT | Yes |
| Paidnice | from **$69** | Xero/QBO + late fees | Yes |
| Knockly | **$29** | Freelancers, Stripe/PayPal links | Yes (schedule) |
| ChaseAI | from **$9** | PDF chase, review before send | After approve |
| InvoiceReminder | from **£19** | Xero/FreeAgent/Sage/QBO | Auto or per-invoice |

Scotive vs that pile: **thread-matched state + pause + owner’s inbox.** Stay on follow-up. Do not add late fees, credit checks, SMS, or invoicing.

---

## 9. What would make $3–10k fail vs work

**Fail:** homepage still “anyone who bills”; SEO that reads like invoice software; ranking for AR automation; waiting on Google instead of LinkedIn; hidden price; selling to one-invoice freelancers.

**Work:** pages 1–2 live; public $29–$49; LinkedIn only to paying titles; first week shows a broken promise or forgotten invoice; cadence actually sending Friendly and actually pausing.

---

## 10. Source index (discussions used)

Reddit (among others):  
https://www.reddit.com/r/smallbusiness/comments/1tmi375/  
https://www.reddit.com/r/Freelancers/comments/1sj14r0/  
https://www.reddit.com/r/agency/comments/1rx30hg/  
https://www.reddit.com/r/smallbusiness/comments/1tw05u4/  
https://www.reddit.com/r/smallbusiness/comments/1qwxo35/  
https://www.reddit.com/r/smallbusiness/comments/1i5ag3r/  
https://www.reddit.com/r/smallbusiness/comments/1tuyjyn/  
https://www.reddit.com/r/smallbusiness/comments/1mh9sdj/  
https://www.reddit.com/r/Solopreneur/comments/1qpc0fd/  
https://www.reddit.com/r/nocode/comments/1u87oub/  
https://www.reddit.com/r/SaaS/comments/1pek3qf/  
https://www.reddit.com/r/povertyfinance/comments/1ji64cs/  
https://www.reddit.com/r/Freelancers/comments/1ucm9bq/  
https://www.reddit.com/r/RealEstatePhotography/comments/133edqm/  
https://www.reddit.com/r/Bookkeeping/comments/1fhn7rb/  
https://www.reddit.com/r/freelance/comments/48ebi9/  

LinkedIn: Nick Saraev; Zainab Oladokun; Alain Ghamachi; Steve Folland; PayPulse (URLs in §3).

Indie Hackers: PayNudger; Dueflo; freelancer follow-up validation; “how to invoice and not get stiffed.”

Stack Exchange: https://freelancing.stackexchange.com/questions/9687/chasing-debts-during-coronavirus-lockdown-uk  

QuickBooks Community: INV-97602; automatic reminders not sending (URLs in §3).

Ahrefs: public Domain Rating 14 Sep 2026; Keywords Explorer tables you pasted (same day).

Product: http://scotive.com/ · https://scotive.com/integrations · https://scotive.com/guides  

---

*End of pack. This file is the working brief for positioning, ICP, LinkedIn, and the six SEO URLs.*
