/** Visible FAQ + matching FAQPage JSON-LD for rich results. */
export function FaqSection({
    items,
    title = "Frequently asked questions",
    eyebrow = "FAQ",
    kicker,
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
                {kicker ?? (eyebrow ? <div className="eyebrow mb-3">{eyebrow}</div> : null)}
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
