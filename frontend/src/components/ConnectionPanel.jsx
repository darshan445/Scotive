import { AlertTriangle, CheckCircle2, Loader2, Mail, Plug } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConnectGmailButton } from "@/components/ConnectGmailButton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useGmailConnection } from "@/hooks/useGmailConnection";

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

export function ConnectionPanel({ status }) {
    const { disconnect } = useGmailConnection();
    const [busy, setBusy] = useState(false);

    async function handleDisconnect() {
        setBusy(true);
        const res = await disconnect();
        setBusy(false);
        if (res.ok) {
            toast("Gmail disconnected", { description: "Cached tokens removed. Your ledger stays." });
        } else {
            toast.error("Couldn't disconnect", { description: res.error });
        }
    }

    if (!status) {
        return (
            <div className="rounded-xl border border-border bg-card p-6 space-y-3" data-testid="connection-panel-loading">
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

    // Not connected
    if (!status.connected || status.status === "disconnected") {
        return (
            <div className="rounded-xl border border-dashed border-border bg-card p-6 flex flex-col sm:flex-row sm:items-center gap-4" data-testid="connection-panel-disconnected">
                <div className="flex items-start gap-3 flex-1">
                    <span className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-muted border border-border">
                        <Mail className="w-5 h-5 text-muted-foreground" />
                    </span>
                    <div>
                        <div className="font-heading font-semibold text-foreground">No Gmail connected</div>
                        <div className="text-sm text-muted-foreground mt-1">
                            Connect your inbox to scan sent invoices and draft chasers.
                        </div>
                    </div>
                </div>
                <ConnectGmailButton label="Connect Gmail" testId="connect-gmail-button" />
            </div>
        );
    }

    // Revoked externally
    if (status.status === "revoked") {
        return (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 flex flex-col md:flex-row md:items-center gap-4" data-testid="connection-panel-revoked">
                <div className="flex items-start gap-3 flex-1">
                    <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5" />
                    <div>
                        <div className="font-heading font-semibold text-amber-900">Gmail access was revoked</div>
                        <div className="text-sm text-amber-800 mt-1">
                            {status.email ? (
                                <>Access to <span className="font-mono">{status.email}</span> was revoked from Google. Reconnect to keep your ledger fresh.</>
                            ) : (
                                <>Reconnect Gmail to keep your ledger fresh.</>
                            )}
                        </div>
                    </div>
                </div>
                <ConnectGmailButton label="Reconnect Gmail" testId="reconnect-gmail-button" />
            </div>
        );
    }

    // Connected but send scope missing
    if (status.status === "send_missing") {
        return (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-6" data-testid="connection-panel-send-missing">
                <div className="flex flex-col md:flex-row md:items-center gap-4">
                    <div className="flex items-start gap-3 flex-1">
                        <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5" />
                        <div>
                            <div className="font-heading font-semibold text-amber-900">Connected — but sending is off</div>
                            <div className="text-sm text-amber-800 mt-1">
                                Ledger will still build from <span className="font-mono">{status.email}</span>, but one-tap chasers are disabled. Reconnect and check the <em>Send email</em> box to enable them.
                            </div>
                        </div>
                    </div>
                    <ConnectGmailButton label="Reconnect Gmail" testId="reconnect-gmail-button" variant="secondary" />
                </div>
                <div className="mt-4 pt-4 border-t border-amber-200 flex flex-wrap items-center justify-between gap-3 text-xs text-amber-900">
                    <span className="font-mono uppercase tracking-[0.18em]">Since {formatDate(status.connected_at)}</span>
                    <Button size="sm" variant="ghost" onClick={handleDisconnect} disabled={busy} data-testid="disconnect-gmail-button">
                        Disconnect
                    </Button>
                </div>
            </div>
        );
    }

    // Fully connected
    return (
        <div className="rounded-xl border border-border bg-card p-6" data-testid="connection-panel-connected">
            <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex items-start gap-3 flex-1">
                    <span className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-200">
                        <CheckCircle2 className="w-5 h-5 text-emerald-700" />
                    </span>
                    <div className="min-w-0">
                        <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Gmail connected</div>
                        <div className="font-heading font-semibold text-lg text-foreground truncate" data-testid="connected-gmail-email">
                            {status.account_name || status.email}
                        </div>
                        {status.account_name && status.email ? (
                            <div className="text-xs font-mono text-muted-foreground truncate">{status.email}</div>
                        ) : null}
                        <div className="text-xs text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                            <span className="inline-flex items-center gap-1"><Mail className="w-3 h-3" /> Read + Send</span>
                            <span className="inline-flex items-center gap-1"><Plug className="w-3 h-3" /> Since {formatDate(status.connected_at)}</span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button size="sm" variant="ghost" onClick={handleDisconnect} disabled={busy} data-testid="disconnect-gmail-button">
                        Disconnect
                    </Button>
                </div>
            </div>
        </div>
    );
}
