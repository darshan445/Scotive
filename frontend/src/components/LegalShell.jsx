import { MarketingShell } from "@/components/MarketingShell";

export function LegalShell({ title, updated, children, testId }) {
    return (
        <MarketingShell testId={testId} activePath="">
            <div className="w-full max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-14">
                <div className="eyebrow mb-3">Legal</div>
                <h1 className="type-display text-3xl md:text-4xl">
                    {title}
                </h1>
                {updated ? (
                    <p className="type-body mt-2 text-sm">Last updated: {updated}</p>
                ) : null}
                <article className="mt-10 legal-prose space-y-8 text-[15px] leading-relaxed text-foreground/90">
                    {children}
                </article>
            </div>
        </MarketingShell>
    );
}

export function LegalSection({ id, title, children }) {
    return (
        <section id={id} className="scroll-mt-24">
            <h2 className="type-title text-xl mb-3">
                {title}
            </h2>
            <div className="space-y-3 text-muted-foreground [&_strong]:text-foreground [&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:space-y-1.5">
                {children}
            </div>
        </section>
    );
}
