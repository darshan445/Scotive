import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { absoluteUrl, SITE_URL } from "@/lib/seo";
import { GUIDES } from "@/lib/guides";

/** Article + soft product CTA wrapper for long-tail guide posts. */
export function GuideArticle({
    guide,
    children,
    testId = "guide-article",
}) {
    const articleLd = {
        "@context": "https://schema.org",
        "@type": "Article",
        headline: guide.title,
        description: guide.description,
        datePublished: guide.published,
        dateModified: guide.published,
        author: {
            "@type": "Organization",
            name: "Scotive",
            url: SITE_URL,
        },
        publisher: {
            "@type": "Organization",
            name: "Scotive",
            url: SITE_URL,
            logo: {
                "@type": "ImageObject",
                url: `${SITE_URL}/logo512.png`,
            },
        },
        mainEntityOfPage: absoluteUrl(guide.path),
    };

    const related = GUIDES.filter((g) => g.slug !== guide.slug).slice(0, 3);

    return (
        <MarketingShell testId={testId} activePath="/guides">
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: JSON.stringify(articleLd) }}
            />
            <MarketingHero
                eyebrow="Guide"
                title={guide.title}
                description={guide.description}
            >
                <p className="mt-4 text-xs text-muted-foreground">
                    Updated {guide.published} · ~5 min read
                </p>
            </MarketingHero>

            <article className="py-12 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="space-y-8 type-body text-muted-foreground [&_h2]:type-title [&_h2]:text-2xl [&_h2]:md:text-3xl [&_h2]:text-foreground [&_h2]:mt-10 [&_h2]:mb-3 [&_p]:leading-relaxed [&_p]:text-sm [&_p]:md:text-base [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:space-y-2 [&_strong]:text-foreground [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:italic [&_pre]:whitespace-pre-wrap [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-border [&_pre]:bg-muted/40 [&_pre]:p-4 [&_pre]:text-sm [&_pre]:text-foreground [&_pre]:font-sans">
                    {children}
                </div>

                <aside className="mt-14 rounded-2xl border border-border bg-muted/30 p-6 md:p-8">
                    <div className="eyebrow mb-2">Scotive</div>
                    <h2 className="type-title text-xl text-foreground">
                        Skip rewriting this follow-up every week
                    </h2>
                    <p className="type-body mt-2 text-sm text-muted-foreground">
                        This guide helps you word one email. Scotive tracks unpaid invoices from Gmail
                        (and QuickBooks), drafts the next chase from real replies — promises, disputes,
                        overdue — and waits for your approval before anything sends.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-3">
                        <Link
                            href="/register"
                            className="inline-flex items-center rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90"
                        >
                            Start free with Scotive
                        </Link>
                        <Link
                            href="/chase-unpaid-invoices"
                            className="inline-flex items-center rounded-xl border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted"
                        >
                            How Scotive chases unpaid invoices
                        </Link>
                    </div>
                </aside>

                {related.length ? (
                    <div className="mt-14">
                        <h2 className="type-title text-xl mb-4">More guides</h2>
                        <ul className="space-y-3">
                            {related.map((g) => (
                                <li key={g.slug}>
                                    <Link
                                        href={g.path}
                                        className="text-sm font-medium text-foreground underline underline-offset-2 hover:opacity-80"
                                    >
                                        {g.title}
                                    </Link>
                                </li>
                            ))}
                            <li>
                                <Link href="/guides" className="text-sm text-muted-foreground hover:text-foreground">
                                    All guides →
                                </Link>
                            </li>
                        </ul>
                    </div>
                ) : null}
            </article>
            <MarketingCta
                title="Use the tip — then automate the chase"
                description="Scotive builds your unpaid-invoice list from email and accounting, drafts the next follow-up, and never sends without you."
                buttonLabel="Start free with Scotive"
            />
        </MarketingShell>
    );
}
