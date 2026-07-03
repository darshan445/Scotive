import { BrandMark } from "@/components/BrandMark";

export function AuthShell({ eyebrow, title, subtitle, children, footer }) {
    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col">
            <header className="px-6 md:px-10 py-6 flex items-center justify-between">
                <BrandMark />
                <div className="hidden sm:flex items-center gap-2 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    Payment ops · Inside Gmail
                </div>
            </header>

            <main className="flex-1 flex items-center justify-center px-6 pb-16">
                <div className="w-full max-w-md">
                    {eyebrow ? (
                        <div className="mb-4 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                            {eyebrow}
                        </div>
                    ) : null}
                    <h1 className="font-heading font-black text-4xl md:text-5xl leading-[1.05] tracking-tight text-foreground">
                        {title}
                    </h1>
                    {subtitle ? (
                        <p className="mt-3 text-base text-muted-foreground leading-relaxed">
                            {subtitle}
                        </p>
                    ) : null}

                    <div className="mt-10">{children}</div>

                    {footer ? (
                        <div className="mt-8 text-sm text-muted-foreground">{footer}</div>
                    ) : null}
                </div>
            </main>

            <footer className="px-6 md:px-10 py-6 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground/70 flex flex-wrap gap-4 justify-between">
                <span>© {new Date().getFullYear()} Scotive</span>
                <span>Read + send-with-approval only · never trained on your emails</span>
            </footer>
        </div>
    );
}
