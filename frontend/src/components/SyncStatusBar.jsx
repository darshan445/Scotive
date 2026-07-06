import { useCallback, useEffect, useState } from "react";
import { Eye, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

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
    return `${Math.floor(hrs / 24)}d ago`;
}

/**
 * Sync strip + live sent-mail watching indicator.
 */
export function SyncStatusBar({ onSynced, watching = false }) {
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
        const t = setInterval(load, 30000);
        return () => clearInterval(t);
    }, [load]);

    useWorkspaceRefreshEffect(load);

    async function syncNow() {
        setBusy(true);
        try {
            const { data } = await api.post("/scan/sync");
            const c = data?.counts || {};
            const live = c.live_detected || 0;
            const newInv = data?.new_invoices || [];
            if (newInv.length > 0) {
                onSynced?.(newInv);
            } else if (live > 0) {
                toast.success(`Synced · ${live} new invoice${live === 1 ? "" : "s"} tracked`);
                onSynced?.();
            } else if (c.skipped === "no_connection") {
                toast.info("Connect Gmail to enable sync.");
            } else if (c.skipped === "auth_error") {
                toast.error("Gmail access expired — reconnect in Settings.");
            } else {
                toast.success("Up to date");
            }
            await load();
            if (!newInv.length) onSynced?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    const checkedAgo = timeAgo(state?.last_detected_at || state?.last_synced_at);
    const isWatching = watching || state?.watching_sent_mail;

    return (
        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2" data-testid="sync-status-bar">
            <div className="flex items-center gap-2 min-w-0">
                {isWatching ? (
                    <span className="relative flex h-2 w-2 flex-shrink-0" data-testid="watching-pulse">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                ) : null}
                <div className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground min-w-0">
                    {isWatching ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-800">
                            <Eye className="w-3.5 h-3.5" />
                            Watching sent mail
                        </span>
                    ) : (
                        <>Sync</>
                    )}
                    {checkedAgo ? (
                        <span className="text-muted-foreground font-normal normal-case tracking-normal ml-1.5">
                            · checked {checkedAgo}
                            {state?.sync_lookback ? (
                                <span className="hidden sm:inline"> · syncs every hour</span>
                            ) : null}
                        </span>
                    ) : (
                        <span className="ml-1.5">· syncs hourly + on demand</span>
                    )}
                </div>
            </div>
            <button
                onClick={syncNow}
                disabled={busy}
                data-testid="sync-now-btn"
                className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest text-foreground hover:text-primary disabled:opacity-50 flex-shrink-0">
                <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
                {busy ? "Syncing…" : "Sync now"}
            </button>
        </div>
    );
}
