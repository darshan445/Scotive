import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import { TopNav } from "@/components/TopNav";
import { EmptyStateHero } from "@/components/EmptyStateHero";
import { ConnectionPanel } from "@/components/ConnectionPanel";
import { ScanProgressCard } from "@/components/ScanProgressCard";
import { LedgerCard } from "@/components/LedgerCard";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { useGmailCallbackToast } from "@/hooks/useGmailCallbackToast";
import { useLedger, useScan } from "@/hooks/useScan";

export default function DashboardPage() {
    const { status, refresh } = useGmailConnection();
    const { state: scanState, startScan, refresh: refreshScan } = useScan();
    const ledgerReady = scanState?.status === "complete";
    const { data: ledger, refresh: refreshLedger } = useLedger(ledgerReady);
    const autoStartedRef = useRef(false);

    useGmailCallbackToast(async (result) => {
        await refresh();
        if (result === "connected" || result === "send_missing") {
            // Trigger a fresh scan right after a successful connect
            autoStartedRef.current = true;
            await startScan(12);
        }
    });

    // If connected but no scan job ever, start one automatically (first landing after connect)
    useEffect(() => {
        if (autoStartedRef.current) return;
        if (!status?.connected) return;
        if (scanState && scanState.has_job === false) {
            autoStartedRef.current = true;
            startScan(12);
        }
    }, [status?.connected, scanState, startScan]);

    // When scan completes, refresh ledger
    useEffect(() => {
        if (scanState?.status === "complete") refreshLedger();
    }, [scanState?.status, refreshLedger]);

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
                    <div className="py-10 md:py-14 space-y-8" data-testid="connected-dashboard">
                        <div className="animate-fade-up">
                            <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">
                                Workspace
                            </div>
                            <h1 className="font-heading font-black text-3xl md:text-4xl tracking-tight text-foreground">
                                Your money ledger
                            </h1>
                            <p className="mt-2 text-base text-muted-foreground">
                                {ledgerReady
                                    ? "Every unpaid invoice we found, with the evidence quote from your inbox."
                                    : "We're reading the last 12 months of your inbox. This usually takes under 2 minutes."}
                            </p>
                        </div>

                        <ConnectionPanel status={status} />

                        {scanState?.has_job && scanState.status !== "complete" ? (
                            <ScanProgressCard state={scanState} />
                        ) : null}

                        {ledgerReady ? <LedgerCard ledger={ledger} /> : null}

                        {scanState?.has_job === false && status.connected ? (
                            <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground" data-testid="scan-idle">
                                Preparing scan…
                            </div>
                        ) : null}
                    </div>
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
