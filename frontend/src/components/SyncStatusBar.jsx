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
export function SyncStatusBar({ onSynced, watching = false, openInvoiceCount = 0 }) {
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
        <div className="inline-flex items-center gap-3 rounded-full border border-border bg-card px-4 py-2 shadow-sm" data-testid="sync-status-bar">
            <div className="flex items-center gap-2 min-w-0">
                {isWatching ? (
                    <span className="relative flex h-2 w-2 flex-shrink-0" data-testid="watching-pulse">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                ) : null}
                <div className="text-xs font-medium text-muted-foreground min-w-0">
                    {isWatching ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-700">
                            <Eye className="w-3.5 h-3.5 flex-shrink-0" />
                            <span className="truncate">
                                Watching {openInvoiceCount} open invoice{openInvoiceCount === 1 ? "" : "s"}
                                {checkedAgo ? (
                                    <span className="text-muted-foreground"> · {checkedAgo}</span>
                                ) : null}
                            </span>
                        </span>
                    ) : (
                        <>
                            Sync
                            {checkedAgo ? (
                                <span className="text-muted-foreground ml-1.5">
                                    · {checkedAgo}
                                </span>
                            ) : null}
                        </>
                    )}
                </div>
            </div>
            <span className="w-px h-4 bg-border" />
            <button
                onClick={syncNow}
                disabled={busy}
                data-testid="sync-now-btn"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-foreground hover:text-accent disabled:opacity-50 flex-shrink-0 transition-colors">
                <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
                {busy ? "Syncing…" : "Sync now"}
            </button>
        </div>
    );
}
