import { GuideArticle } from "@/components/GuideArticle";
import { getGuide } from "@/lib/guides";
import { pageMetadata } from "@/lib/seo";

const guide = getGuide("invoice-follow-up-email-templates");

export const metadata = pageMetadata({
    title: guide.title,
    description: guide.description,
    path: guide.path,
    keywords: guide.keywords,
});

export default function Page() {
    return (
        <GuideArticle guide={guide} testId="guide-invoice-templates">
            <p>
                Most people don&apos;t struggle to <em>know</em> they should follow up on an unpaid invoice.
                They struggle to write the email without sounding desperate, rude, or like a robot.
            </p>
            <p>
                Below are invoice follow-up email templates you can copy — a friendly nudge, a firm unpaid
                invoice reminder, and a final notice. Swap the brackets for your details and send from your
                own address.
            </p>

            <h2>What makes a good invoice follow-up</h2>
            <ul>
                <li>
                    <strong>Specifics</strong> — invoice number, amount, and original send or due date
                </li>
                <li>
                    <strong>One ask</strong> — confirm payment timing or raise a question; don&apos;t dump
                    your whole ledger
                </li>
                <li>
                    <strong>Tone that matches lateness</strong> — day 3 after due is not the same as day 45
                </li>
                <li>
                    <strong>An easy reply</strong> — &quot;Did this land?&quot; beats a wall of legal language
                </li>
            </ul>

            <h2>Template 1 — Friendly invoice follow-up (just past due)</h2>
            <p>Use when the due date recently slipped and you still assume good intent.</p>
            <pre>{`Subject: Quick check-in on invoice [INV-2041]

Hi [Name],

Hope you're well. Just following up on invoice [INV-2041] for [amount], sent on [date] (due [due date]).

Wanted to make sure it didn't get buried — happy to resend the PDF or answer any questions on the line items.

Thanks,
[Your name]`}</pre>

            <h2>Template 2 — Unpaid invoice reminder (firm, still polite)</h2>
            <p>Use when you&apos;ve already nudged once, or they&apos;re clearly overdue with no reply.</p>
            <pre>{`Subject: Reminder: invoice [INV-2041] still open ([amount])

Hi [Name],

I'm following up again on invoice [INV-2041] for [amount], originally due [due date]. I haven't seen payment land yet.

If there's a blocker on your side — PO, revised amount, timing — just say the word and we can sort it. Otherwise, could you confirm when payment will go out?

Appreciate it,
[Your name]`}</pre>

            <h2>Template 3 — Final notice (relationship-safe)</h2>
            <p>Use after silence or broken promises. Clear, not theatrical.</p>
            <pre>{`Subject: Final follow-up on invoice [INV-2041]

Hi [Name],

This is my final follow-up on invoice [INV-2041] for [amount], outstanding since [due date].

Please arrange payment by [date], or reply with the status on your end so I know how to proceed. I'm happy to send a fresh copy of the invoice if that helps.

Thanks,
[Your name]`}</pre>

            <h2>Invoice reminder email sample — after they promised a date</h2>
            <p>
                If they said &quot;paying Friday&quot; and Friday passed, reference the promise. That&apos;s
                more effective than a generic reminder for an unpaid invoice.
            </p>
            <pre>{`Subject: Following up on [INV-2041] — Friday payment

Hi [Name],

You mentioned payment on [INV-2041] ([amount]) would go out by last Friday. I haven't seen it yet — did something shift on timing?

Happy to adjust if you need a new date; just want to keep this closed out.

Thanks,
[Your name]`}</pre>

            <h2>Tips before you hit send</h2>
            <ol>
                <li>Send from the same thread as the original invoice when you can.</li>
                <li>Don&apos;t attach guilt essays — attach the PDF only if they asked or it might be lost.</li>
                <li>Escalate tone across touches; don&apos;t start at &quot;final notice.&quot;</li>
                <li>Stop chasing the moment you confirm payment — no leftover nags.</li>
            </ol>
            <p>
                For more on timing and tone, see{" "}
                <a href="/guides/polite-reminder-for-unpaid-invoice">how to send a polite unpaid invoice reminder</a>
                {" "}and{" "}
                <a href="/guides/how-to-follow-up-on-an-invoice-politely">how to politely follow up on an invoice</a>.
            </p>
        </GuideArticle>
    );
}
