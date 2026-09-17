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
    if (seconds < 45) return "just now";
    const mins = Math.floor(seconds / 60);
    if (mins < 60) return mins === 1 ? "1 minute ago" : `${mins} minutes ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs === 1 ? "1 hour ago" : `${hrs} hours ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return days === 1 ? "1 day ago" : `${days} days ago`;
    const months = Math.floor(days / 30);
    return months === 1 ? "1 month ago" : `${months} months ago`;
}

/**
 * Sync strip + live sent-mail watching indicator.
 */
export function SyncStatusBar({ onSynced, watching = false, openInvoiceCount = 0 }) {
    const [state, setState] = useState(null);
    const [busy, setBusy] = useState(false);
    const [nowTick, setNowTick] = useState(0);

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

    // Refresh relative labels without waiting for the next sync-state poll.
    useEffect(() => {
        const t = setInterval(() => setNowTick((n) => n + 1), 60000);
        return () => clearInterval(t);
    }, []);

    useWorkspaceRefreshEffect(load);

    async function syncNow() {
        setBusy(true);
        try {
            const { data } = await api.post("/scan/sync");
            const c = data?.counts || {};
            const live = c.live_detected || 0;
            const qboCreated = (c.qbo_cdc && (c.qbo_cdc.created || 0)) || 0;
            if (live > 0 || qboCreated > 0) {
                const n = live || qboCreated;
                toast.success(`Synced · ${n} new invoice${n === 1 ? "" : "s"} from QuickBooks`);
                onSynced?.();
            } else if (c.skipped === "no_connection") {
                toast.info("Connect Gmail or Outlook to match conversations.");
            } else if (c.skipped === "auth_error") {
                toast.error("Mailbox access expired — reconnect in Settings.");
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

    // Prefer last completed sync; fall back to last detect stamp.
    void nowTick; // keep relative label current
    const lastSyncIso = state?.last_synced_at || state?.last_detected_at;
    const syncedAgo = timeAgo(lastSyncIso);
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
                        <span className="inline-flex items-center gap-1.5 min-w-0">
                            <Eye className="w-3.5 h-3.5 flex-shrink-0 text-emerald-700" />
                            <span className="truncate text-emerald-700">
                                Watching {openInvoiceCount} open invoice{openInvoiceCount === 1 ? "" : "s"}
                            </span>
                            {syncedAgo ? (
                                <span className="truncate text-muted-foreground" data-testid="sync-last-ago">
                                    · Last sync {syncedAgo}
                                </span>
                            ) : null}
                        </span>
                    ) : (
                        <>
                            Sync
                            {syncedAgo ? (
                                <span className="text-muted-foreground ml-1.5" data-testid="sync-last-ago">
                                    · Last sync {syncedAgo}
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
