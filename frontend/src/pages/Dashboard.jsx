import { Loader2 } from "lucide-react";
import { TopNav } from "@/components/TopNav";
import { EmptyStateHero } from "@/components/EmptyStateHero";
import { ConnectionPanel } from "@/components/ConnectionPanel";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { useGmailCallbackToast } from "@/hooks/useGmailCallbackToast";

export default function DashboardPage() {
    const { status, refresh } = useGmailConnection();
    useGmailCallbackToast(() => refresh());

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="dashboard-root">
            <TopNav />
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {status === null ? (
                    <div className="py-32 flex items-center justify-center text-muted-foreground text-sm" data-testid="dashboard-loading">
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Loading your workspace…
                    </div>
                ) : status.connected || status.status === "revoked" ? (
                    <ConnectedDashboard status={status} />
                ) : (
                    <EmptyStateHero />
                )}
            </main>

            <footer className="border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-wrap justify-between items-center gap-3 text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    <span>© {new Date().getFullYear()} Scotive</span>
                    <span>Payment ops · Inside Gmail</span>
                </div>
            </footer>
        </div>
    );
}

function ConnectedDashboard({ status }) {
    return (
        <div className="py-10 md:py-14 space-y-8" data-testid="connected-dashboard">
            <div className="animate-fade-up">
                <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">
                    Workspace
                </div>
                <h1 className="font-heading font-black text-3xl md:text-4xl tracking-tight text-foreground">
                    Your money ledger
                </h1>
                <p className="mt-2 text-base text-muted-foreground">
                    Gmail is connected. The historical scan (Feature 4) will populate the ledger here.
                </p>
            </div>

            <ConnectionPanel status={status} />

            <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center" data-testid="ledger-placeholder">
                <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">
                    Next up
                </div>
                <h2 className="font-heading font-semibold text-xl md:text-2xl tracking-tight">
                    Historical scan is Feature 4
                </h2>
                <p className="mt-2 text-sm text-muted-foreground max-w-xl mx-auto">
                    Once you approve this feature, we&apos;ll wire the 12-month inbox scan and populate your ledger with real invoices and evidence.
                </p>
            </div>
        </div>
    );
}
