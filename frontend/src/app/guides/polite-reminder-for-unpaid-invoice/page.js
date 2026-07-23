import { GuideArticle } from "@/components/GuideArticle";
import { getGuide } from "@/lib/guides";
import { pageMetadata } from "@/lib/seo";

const guide = getGuide("polite-reminder-for-unpaid-invoice");

export const metadata = pageMetadata({
    title: guide.title,
    description: guide.description,
    path: guide.path,
    keywords: guide.keywords,
});

export default function Page() {
    return (
        <GuideArticle guide={guide} testId="guide-unpaid-reminder">
            <p>
                An unpaid invoice reminder should feel like a clear nudge — not a confrontation. The goal is
                simple: remind them what&apos;s open, make it easy to pay or reply, and protect the
                relationship.
            </p>

            <h2>When to send a reminder for an unpaid invoice</h2>
            <ul>
                <li>
                    <strong>1–3 days after due</strong> — friendly check-in (&quot;did this land?&quot;)
                </li>
                <li>
                    <strong>7–14 days overdue</strong> — clearer unpaid invoice reminder with amount + due date
                </li>
                <li>
                    <strong>After a broken promise</strong> — reference the date they gave you
                </li>
                <li>
                    <strong>Long silence</strong> — firmer ask with a concrete next step or deadline
                </li>
            </ul>
            <p>
                If they already disputed a line item or asked a question, answer that first. A blind reminder
                for an unpaid invoice on top of an open dispute feels tone-deaf.
            </p>

            <h2>A polite unpaid invoice reminder you can send</h2>
            <pre>{`Subject: Reminder — invoice [INV-2041] ([amount])

Hi [Name],

Quick reminder that invoice [INV-2041] for [amount] was due on [due date] and still shows as unpaid on my side.

If payment is already in motion, great — ignore this. If anything's unclear on the invoice, reply and I'll sort it.

Thanks,
[Your name]`}</pre>

            <h2>Three rules that keep reminders polite</h2>
            <ol>
                <li>
                    <strong>Assume competence, not bad faith.</strong> Most late payments are process, not
                    spite.
                </li>
                <li>
                    <strong>Put the facts up front.</strong> Number, amount, due date — then the ask.
                </li>
                <li>
                    <strong>Offer an off-ramp.</strong> &quot;If something&apos;s blocking payment, tell me&quot;
                    lowers defensiveness and often surfaces the real issue.
                </li>
            </ol>

            <h2>What not to do</h2>
            <ul>
                <li>All-caps subject lines or &quot;URGENT SECOND NOTICE&quot; on the first overdue day</li>
                <li>CC&apos;ing their boss before you&apos;ve tried a normal reminder</li>
                <li>Threatening legal action in the first or second email</li>
                <li>Sending the same generic reminder forever with no tone change</li>
            </ul>

            <h2>A simple reminder cadence</h2>
            <p>
                Day 0: invoice. Day +due+2: friendly follow-up. Day +10: unpaid invoice reminder. Day +21:
                firmer note. After that, decide whether to escalate, pause work, or write it off — based on
                the relationship, not emotion in the moment.
            </p>
            <p>
                Need copy-paste variants? See{" "}
                <a href="/guides/invoice-follow-up-email-templates">invoice follow-up email templates</a>.
                If they promised a date and missed it, read{" "}
                <a href="/guides/client-said-ill-pay-friday">what to do when they said &quot;I&apos;ll pay Friday&quot;</a>.
            </p>
        </GuideArticle>
    );
}
