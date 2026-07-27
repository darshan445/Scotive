import Link from "next/link";

export function AppFooter({ compact = false }) {
    return (
        <footer className="border-t border-border mt-auto" data-testid="app-footer">
            <div
                className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-wrap justify-between items-center gap-3 text-xs text-muted-foreground ${
                    compact ? "py-5" : "py-6"
                }`}
            >
                <span>© {new Date().getFullYear()} Scotive</span>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                    <Link href="/contact" className="hover:text-foreground transition-colors">
                        Contact
                    </Link>
                    <Link href="/terms" className="hover:text-foreground transition-colors">
                        Terms
                    </Link>
                    <Link href="/privacy" className="hover:text-foreground transition-colors">
                        Privacy
                    </Link>
                    <Link href="/integrations" className="hover:text-foreground transition-colors hidden sm:inline">
                        Integrations
                    </Link>
                    <span className="hidden md:inline">Get paid faster · You approve every send</span>
                </div>
            </div>
        </footer>
    );
}
