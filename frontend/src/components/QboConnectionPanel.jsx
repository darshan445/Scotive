import { AlertTriangle, CheckCircle2, Loader2, Plug } from "lucide-react";
import { SiQuickbooks } from "react-icons/si";
import { useState } from "react";
import { toast } from "sonner";
import { ConnectQboButton } from "@/components/ConnectQboButton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, extractError, unwrapData, LONG_JOB_TIMEOUT_MS } from "@/lib/api";
import { useQboConnection } from "@/hooks/useQboConnection";
import { notifyWorkspaceRefresh } from "@/lib/workspaceRefresh";
import { needsReconnect } from "@/lib/connectionStatus";
function formatDate(iso) {
    if (!iso) return "";
    try {
        return new Date(iso).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return "";
    }
}

export function QboConnectionPanel({ status }) {
    const { disconnect, refresh } = useQboConnection();
    const [busy, setBusy] = useState(false);
    const [importing, setImporting] = useState(false);

    async function handleDisconnect() {
        setBusy(true);
        const res = await disconnect();
        setBusy(false);
        if (res.ok) {
            toast("QuickBooks disconnected", {
                description: "Cached tokens removed. Your ledger stays.",
            });
        } else {
            toast.error("Couldn't disconnect", { description: res.error });
        }
    }

    async function handleImport() {
        setImporting(true);
        try {
            const { data } = await api.post("/v1/qbo/import", null, { timeout: LONG_JOB_TIMEOUT_MS });
            const c = unwrapData(data)?.counts || {};
            const created = c.created || 0;
            const updated = c.updated || 0;
            const merged = c.merged || 0;
            const fetched = c.fetched || 0;
            if (fetched === 0) {
                toast.success("No open QuickBooks invoices", {
                    description: "Nothing with a remaining balance to import.",
                });
            } else {
                toast.success("QuickBooks import complete", {
                    description: `${created} new · ${updated} updated · ${merged} linked · ${fetched} fetched`,
                });
            }
            await refresh();
            notifyWorkspaceRefresh();
        } catch (e) {
            toast.error("Import failed", { description: extractError(e) });
        } finally {
            setImporting(false);
        }
    }

    if (!status) {
        return (
            <div className="rounded-xl border border-border bg-card p-6 space-y-3" data-testid="qbo-connection-panel-loading">
                <div className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-lg flex-shrink-0" />
                    <div className="space-y-2 flex-1">
                        <Skeleton className="h-4 w-40" />
                        <Skeleton className="h-3 w-56 max-w-full" />
                    </div>
                </div>
            </div>
        );
    }

    if (needsReconnect(status.status)) {
        return (
            <div
                className="rounded-xl border border-amber-200 bg-amber-50 p-6 flex flex-col md:flex-row md:items-center gap-4"
                data-testid="qbo-connection-panel-revoked"
            >
                <div className="flex items-start gap-3 flex-1">
                    <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5" />
                    <div>
                        <div className="font-heading font-semibold text-amber-900">QuickBooks access was revoked</div>
                        <div className="text-sm text-amber-800 mt-1">
                            Reconnect to keep importing invoices and paid status from QuickBooks.
                            {status.company_name ? (
                                <> ({status.company_name})</>
                            ) : null}
                        </div>
                    </div>
                </div>
                <ConnectQboButton label="Reconnect QuickBooks" testId="reconnect-qbo-button" />
            </div>
        );
    }

    if (!status.connected || status.status === "disconnected") {
        return (
            <div
                className="rounded-xl border border-dashed border-border bg-card p-6 flex flex-col sm:flex-row sm:items-center gap-4"
                data-testid="qbo-connection-panel-disconnected"
            >
                <div className="flex items-start gap-3 flex-1">
                    <span className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-muted border border-border">
                        <SiQuickbooks className="w-5 h-5 text-muted-foreground" />
                    </span>
                    <div>
                        <div className="font-heading font-semibold text-foreground">No QuickBooks connected</div>
                        <div className="text-sm text-muted-foreground mt-1">
                            Optional — link QuickBooks to import open invoices. Gmail still handles conversations.
                        </div>
                    </div>
                </div>
                <ConnectQboButton label="Connect QuickBooks" testId="connect-qbo-button" variant="secondary" />
            </div>
        );
    }

    return (
        <div className="rounded-xl border border-border bg-card p-6" data-testid="qbo-connection-panel-connected">
            <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex items-start gap-3 flex-1">
                    <span className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-200">
                        <CheckCircle2 className="w-5 h-5 text-emerald-700" />
                    </span>
                    <div className="min-w-0">
                        <div className="eyebrow">
                            QuickBooks connected
                        </div>
                        <div
                            className="font-heading font-semibold text-lg text-foreground truncate"
                            data-testid="connected-qbo-label"
                        >
                            {status.company_name || "QuickBooks company"}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                            {status.env ? (
                                <span className="font-mono uppercase tracking-wider">{status.env}</span>
                            ) : null}
                            {status.realm_id ? (
                                <span className="font-mono truncate" title={status.realm_id}>
                                    Realm {status.realm_id}
                                </span>
                            ) : null}
                            <span className="inline-flex items-center gap-1">
                                <Plug className="w-3 h-3" /> Since {formatDate(status.connected_at)}
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <Button
                        size="sm"
                        variant="secondary"
                        onClick={handleImport}
                        disabled={importing || busy}
                        data-testid="import-qbo-invoices-button"
                    >
                        {importing ? (
                            <>
                                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                                Importing…
                            </>
                        ) : (
                            "Import open invoices"
                        )}
                    </Button>
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleDisconnect}
                        disabled={busy || importing}
                        data-testid="disconnect-qbo-button"
                    >
                        Disconnect
                    </Button>
                </div>
            </div>
        </div>
    );
}
