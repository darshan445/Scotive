import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";

function timeAgo(iso) {
    if (!iso) return null;
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return null;
    const seconds = Math.max(0, Math.floor((Date.now() - dt.getTime()) / 1000));
    if (seconds < 60) return `${seconds}s ago`;
    const mins = Math.floor(seconds / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
}

/**
 * Compact sync-status strip. Shows "Last synced <ago>" plus a Sync-now button.
 * Refreshes ledger/receipts after a successful sync via `onSynced`.
 */
export function SyncStatusBar({ onSynced }) {
    const [state, setState] = useState(null);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            const { data } = await api.get("/scan/sync-state");
            setState(data);
        } catch {
            /* ignore */
        }
    }, []);

    useEffect(() => {
        load();
        // Also refresh every 30s so the "ago" label stays fresh
        const t = setInterval(load, 30000);
        return () => clearInterval(t);
    }, [load]);

    async function syncNow() {
        setBusy(true);
        try {
            const { data } = await api.post("/scan/sync");
            const c = data?.counts || {};
            const added = (c.invoices_created || 0) + (c.receipts_created || 0) + (c.review_items || 0);
            if (added > 0) {
                toast.success(`Synced · ${c.invoices_created || 0} inv · ${c.receipts_created || 0} pmt · ${c.review_items || 0} review`);
            } else if (c.skipped === "no_connection") {
                toast.info("Connect Gmail to enable sync.");
            } else if (c.skipped === "auth_error") {
                toast.error("Gmail access expired — reconnect from the top of the page.");
            } else {
                toast.success("Up to date");
            }
            await load();
            onSynced?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    const ago = timeAgo(state?.last_synced_at);
    return (
        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2" data-testid="sync-status-bar">
            <div className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                {ago ? (
                    <>Last synced <span data-testid="sync-last-ago">{ago}</span></>
                ) : (
                    <>Sync pending — Scotive will pull new mail every 5 minutes.</>
                )}
                {state?.last_sync_status === "auth_error" ? (
                    <span className="ml-2 text-red-700">Gmail auth expired</span>
                ) : null}
            </div>
            <button
                onClick={syncNow}
                disabled={busy}
                data-testid="sync-now-btn"
                className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest text-foreground hover:text-primary disabled:opacity-50">
                <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
                {busy ? "Syncing…" : "Sync now"}
            </button>
        </div>
    );
}
