/** Visible FAQ + matching FAQPage JSON-LD for rich results. */
export function FaqSection({
    items,
    title = "Frequently asked questions",
    eyebrow = "FAQ",
}) {
    const faqLd = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: items.map((item) => ({
            "@type": "Question",
            name: item.question,
            acceptedAnswer: {
                "@type": "Answer",
                text: item.answer,
            },
        })),
    };

    return (
        <section className="py-16 md:py-20 border-t border-border/70" data-testid="faq-section">
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: JSON.stringify(faqLd) }}
            />
            <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                {eyebrow ? <div className="eyebrow mb-3">{eyebrow}</div> : null}
                <h2 className="type-title text-3xl md:text-4xl">{title}</h2>
                <dl className="mt-10 space-y-8">
                    {items.map((item) => (
                        <div key={item.question}>
                            <dt className="type-title text-lg text-foreground">{item.question}</dt>
                            <dd className="type-body mt-2 text-sm md:text-base text-muted-foreground">
                                {item.answer}
                            </dd>
                        </div>
                    ))}
                </dl>
            </div>
        </section>
    );
}

export const HOME_FAQS = [
    {
        question: "Does Scotive auto-send emails?",
        answer:
            "No. Scotive drafts follow-ups based on invoice state, but nothing is sent until you review and approve. You stay in control of every client email.",
    },
    {
        question: "Is my email content used to train AI models?",
        answer:
            "No. Email content connected to Scotive is not used to train Scotive's models. You can disconnect integrations and delete your account anytime.",
    },
    {
        question: "What email and accounting tools does Scotive support?",
        answer:
            "Gmail and QuickBooks Online are available now. Outlook / Microsoft 365, Zoho Books, and FreshBooks are on the roadmap — Scotive is built for email + accounting, not one vendor only.",
    },
    {
        question: "Who is Scotive for?",
        answer:
            "Freelancers, agencies, consultants, professional services, and any team that bills clients and chases unpaid invoices — without needing an enterprise collections stack.",
    },
    {
        question: "How is Scotive different from Chaser or Upflow?",
        answer:
            "Those tools often automate AR sequences for finance teams. Scotive watches the conversations and invoices you already have, drafts the next follow-up in context, and never sends without your click.",
    },
];
