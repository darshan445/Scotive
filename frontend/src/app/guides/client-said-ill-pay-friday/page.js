import { GuideArticle } from "@/components/GuideArticle";
import { getGuide } from "@/lib/guides";
import { pageMetadata } from "@/lib/seo";

const guide = getGuide("client-said-ill-pay-friday");

export const metadata = pageMetadata({
    title: guide.title,
    description: guide.description,
    path: guide.path,
    keywords: guide.keywords,
});

export default function Page() {
    return (
        <GuideArticle guide={guide} testId="guide-pay-friday">
            <p>
                &quot;Paying Friday&quot; feels like progress — until Friday comes and goes. Broken payment
                promises are one of the most common reasons invoices stay open. Here&apos;s how to follow up
                without turning the relationship into a fight.
            </p>

            <h2>Why &quot;I&apos;ll pay Friday&quot; fails so often</h2>
            <ul>
                <li>They meant it, then payroll / AP / a boss delayed it</li>
                <li>They needed a reminder and never put it on a calendar</li>
                <li>They were buying time and hoped you wouldn&apos;t notice</li>
            </ul>
            <p>
                You usually can&apos;t tell which from the outside. So treat the first miss as a process
                failure, not a character judgment — then get specific.
            </p>

            <h2>What to do the next business day</h2>
            <ol>
                <li>
                    <strong>Confirm nothing landed.</strong> Check bank / accounting before you accuse.
                </li>
                <li>
                    <strong>Reply in the same thread</strong> where they made the promise.
                </li>
                <li>
                    <strong>Quote the date they gave.</strong> Specificity beats a generic chase.
                </li>
                <li>
                    <strong>Ask for a new date or a blocker.</strong> Either answer is useful.
                </li>
            </ol>

            <h2>Email when Friday came and went</h2>
            <pre>{`Subject: Re: [INV-2041] — Friday payment

Hi [Name],

You mentioned payment for invoice [INV-2041] ([amount]) would go out by Friday. I haven't seen it yet — did the timing shift?

If you can share an updated date (or what's blocking it), I'll adjust on my side. Happy to resend the invoice if that helps.

Thanks,
[Your name]`}</pre>

            <h2>If they promise again — and miss again</h2>
            <p>
                Second broken promise: tighten the tone. Still polite, less soft. Offer one clear path:
                pay by a date you set, or pause further work until the balance clears (if your contract
                allows).
            </p>
            <pre>{`Hi [Name] — following up again on INV-2041. The Friday date and the follow-up date both passed without payment.

I need this settled by [date], or a written plan I can rely on. If there's a dispute on scope or amount, tell me now so we can resolve that instead of another missed transfer.

Thanks,
[Your name]`}</pre>

            <h2>Track promises like due dates</h2>
            <p>
                The operational mistake is treating &quot;paying Friday&quot; as vibes. Write the promise
                date down next to the invoice. When it slips, that&apos;s your cue for a firmer follow-up —
                same as an overdue due date.
            </p>
            <p>
                For wording that stays polite earlier in the cycle, see{" "}
                <a href="/guides/how-to-follow-up-on-an-invoice-politely">how to politely follow up on an invoice</a>
                {" "}and{" "}
                <a href="/guides/invoice-follow-up-email-templates">invoice follow-up email templates</a>.
            </p>
        </GuideArticle>
    );
}
