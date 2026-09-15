import Link from "next/link";
import { relatedResources } from "@/lib/guides";
import { PRICE_AFTER_TRIAL } from "@/lib/site";

export function SeoEyebrow({ index, children }) {
    const n = String(index).padStart(2, "0");
    return (
        <div className="flex items-center gap-3 mb-4">
            <span className="inline-flex items-center justify-center min-w-[2.25rem] h-9 px-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold tabular-nums">
                {n}
            </span>
            <span className="text-base md:text-lg font-semibold tracking-tight text-foreground">
                {children}
            </span>
            <span className="hidden sm:block h-px flex-1 max-w-[7rem] bg-border" aria-hidden />
        </div>
    );
}

export function SeoCard({ title, detail, badge }) {
    return (
        <div className="surface-card p-6">
            {badge ? (
                <div className="text-[11px] font-semibold text-primary mb-3">{badge}</div>
            ) : null}
            <h3 className="type-title text-lg leading-snug">{title}</h3>
            <p className="type-body mt-3 text-sm">{detail}</p>
        </div>
    );
}

export function EmailTemplate({ label, subject, body }) {
    return (
        <article className="surface-card p-6">
            <div className="text-[11px] font-semibold text-primary mb-3">{label}</div>
            <p className="text-sm text-foreground">
                <span className="text-muted-foreground">Subject: </span>
                {subject}
            </p>
            <pre className="type-body mt-4 rounded-lg border border-border bg-muted/40 p-4 text-sm text-foreground whitespace-pre-wrap font-sans">
                {body}
            </pre>
        </article>
    );
}

export function RelatedResources({ currentPath }) {
    const items = relatedResources(currentPath);
    if (!items.length) return null;
    return (
        <nav className="py-12 md:py-16 border-t border-border/70" aria-label="Related pages">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <h2 className="type-title text-xl md:text-2xl">More on follow-up</h2>
                <ul className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {items.map((item) => (
                        <li key={item.path}>
                            <Link
                                href={item.path}
                                className="surface-card p-5 hover:shadow-md transition-shadow block h-full"
                            >
                                <h3 className="type-title text-base">{item.title}</h3>
                                <p className="type-body mt-1.5 text-sm">{item.description}</p>
                            </Link>
                        </li>
                    ))}
                </ul>
                <p className="type-body mt-8 text-sm text-muted-foreground">
                    {PRICE_AFTER_TRIAL}
                </p>
            </div>
        </nav>
    );
}
