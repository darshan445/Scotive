import { GuideArticle } from "@/components/GuideArticle";
import { getGuide } from "@/lib/guides";
import { pageMetadata } from "@/lib/seo";

const guide = getGuide("how-to-follow-up-on-an-invoice-politely");

export const metadata = pageMetadata({
    title: guide.title,
    description: guide.description,
    path: guide.path,
    keywords: guide.keywords,
});

export default function Page() {
    return (
        <GuideArticle guide={guide} testId="guide-polite-follow-up">
            <p>
                Knowing how to politely follow up on an invoice is less about clever wording and more about
                timing, clarity, and not writing when you&apos;re angry. Here&apos;s a calm process that
                works for freelancers, agencies, and anyone who bills clients.
            </p>

            <h2>1. Wait for the due date (then a short buffer)</h2>
            <p>
                Following up the morning after you sent the invoice usually feels pushy. Wait until it&apos;s
                actually due — then give 1–2 business days for bank transfer lag — before your first polite
                follow-up.
            </p>

            <h2>2. Lead with context, not emotion</h2>
            <p>
                Open with invoice number, amount, and date. Skip &quot;I hate to bother you&quot; and skip
                &quot;as discussed repeatedly.&quot; A polite invoice follow-up sounds adult: facts, then one
                clear ask.
            </p>
            <pre>{`Hi [Name] — checking in on INV-2041 ($2,400), due last Tuesday. Did it arrive okay, or is there anything you need from me?`}</pre>

            <h2>3. Match tone to how late it is</h2>
            <ul>
                <li>Slightly late → curious and helpful</li>
                <li>Clearly overdue → direct reminder</li>
                <li>Broken promise → reference their date, ask for a new one</li>
                <li>Long silence → firm, still professional</li>
            </ul>
            <p>
                Jumping straight to a final notice trains clients to ignore your early emails. Escalate in
                steps.
            </p>

            <h2>4. Make the next step obvious</h2>
            <p>
                Good asks: &quot;Can you confirm payment this week?&quot; / &quot;Want me to resend the
                PDF?&quot; / &quot;Is there a PO or approval stuck?&quot; Bad asks: vague &quot;circling
                back&quot; with no invoice reference.
            </p>

            <h2>5. Keep it in-thread when possible</h2>
            <p>
                Reply on the original invoice email so they have history and the attachment nearby. New
                threads get lost — and make you look like you&apos;re starting a campaign.
            </p>

            <h2>6. Stop when you&apos;re paid (or when they dispute)</h2>
            <p>
                How to politely follow up on an invoice also means knowing when to switch modes. If they
                dispute a line, resolve the dispute before more payment nudges. If they paid, send a short
                thanks — not another reminder that was already queued in your head.
            </p>

            <h2>Short polite follow-up you can use today</h2>
            <pre>{`Subject: Following up on [INV-2041]

Hi [Name],

Just following up on invoice [INV-2041] for [amount], due [due date]. Wanted to check whether it's in your payment queue or if anything looks off on your end.

Thanks so much,
[Your name]`}</pre>

            <p>
                More templates:{" "}
                <a href="/guides/invoice-follow-up-email-templates">invoice follow-up email templates</a>.
                Reminder timing:{" "}
                <a href="/guides/polite-reminder-for-unpaid-invoice">polite reminder for an unpaid invoice</a>.
            </p>
        </GuideArticle>
    );
}
