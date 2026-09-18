import { AlertTriangle, CheckCircle2, Loader2, Mail, Plug } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConnectMailboxButton } from "@/components/ConnectGmailButton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useGmailConnection } from "@/hooks/useGmailConnection";
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

function providerLabel(provider) {
    return provider === "outlook" ? "Outlook" : "Gmail";
}

function connFor(status, provider) {
    const list = status?.connections || [];
    const hit = list.find((c) => c.provider === provider);
    if (hit) return hit;
    // Legacy single-connection responses
    if (status?.connected && (status.provider || "google") === provider) {
        return status;
    }
    return { provider, connected: false, status: "disconnected" };
}

function MailboxRow({ provider, conn, onDisconnect, busy }) {
    const label = providerLabel(provider);
    const revoked = needsReconnect(conn?.status);
    const connected = Boolean(conn?.connected) && !revoked;

    return (
        <div
            className="rounded-xl border border-border bg-card p-5 flex flex-col sm:flex-row sm:items-center gap-4"
            data-testid={`mailbox-row-${provider}`}
        >
            <div className="flex items-start gap-3 flex-1 min-w-0">
                <span
                    className={`inline-flex items-center justify-center w-10 h-10 rounded-lg border flex-shrink-0 ${
                        connected
                            ? "bg-emerald-50 border-emerald-200"
                            : revoked
                              ? "bg-amber-50 border-amber-200"
                              : "bg-muted border-border"
                    }`}
                >
                    {connected ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-700" />
                    ) : revoked ? (
                        <AlertTriangle className="w-5 h-5 text-amber-700" />
                    ) : (
                        <Mail className="w-5 h-5 text-muted-foreground" />
                    )}
                </span>
                <div className="min-w-0">
                    <div className="font-heading font-semibold text-foreground">{label}</div>
                    {connected ? (
                        <>
                            <div className="text-sm text-foreground truncate" data-testid={`connected-${provider}-email`}>
                                {conn.account_name || conn.email}
                            </div>
                            {conn.account_name && conn.email ? (
                                <div className="text-xs font-mono text-muted-foreground truncate">{conn.email}</div>
                            ) : null}
                            <div className="text-xs text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                                <span className="inline-flex items-center gap-1"><Mail className="w-3 h-3" /> Read + Send</span>
                                <span className="inline-flex items-center gap-1"><Plug className="w-3 h-3" /> Since {formatDate(conn.connected_at)}</span>
                            </div>
                        </>
                    ) : revoked ? (
                        <div className="text-sm text-amber-800 mt-0.5">
                            Access was revoked{conn.email ? <> for <span className="font-mono">{conn.email}</span></> : null}. Reconnect to keep syncing.
                        </div>
                    ) : (
                        <div className="text-sm text-muted-foreground mt-0.5">
                            Optional — connect if you send invoices from {label}.
                        </div>
                    )}
                </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
                {connected ? (
                    <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onDisconnect(provider)}
                        data-testid={`disconnect-${provider}-button`}
                    >
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Disconnect"}
                    </Button>
                ) : (
                    <ConnectMailboxButton
                        provider={provider}
                        label={revoked ? `Reconnect ${label}` : `Connect ${label}`}
                        testId={`connect-${provider}-button`}
                        variant={provider === "outlook" ? "secondary" : "primary"}
                    />
                )}
            </div>
        </div>
    );
}

export function ConnectionPanel({ status }) {
    const { disconnect } = useGmailConnection();
    const [busyProvider, setBusyProvider] = useState(null);

    async function handleDisconnect(provider) {
        setBusyProvider(provider);
        const res = await disconnect(provider);
        setBusyProvider(null);
        if (res.ok) {
            toast(`${providerLabel(provider)} disconnected`, {
                description: "Your ledger stays. Other mailboxes are unchanged.",
            });
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

    return (
        <div className="space-y-3" data-testid="connection-panel">
            <p className="text-sm text-muted-foreground">
                Connect Gmail, Outlook, or both — Scotive tracks invoices across every linked mailbox.
            </p>
            <MailboxRow
                provider="google"
                conn={connFor(status, "google")}
                onDisconnect={handleDisconnect}
                busy={busyProvider === "google"}
            />
            <MailboxRow
                provider="outlook"
                conn={connFor(status, "outlook")}
                onDisconnect={handleDisconnect}
                busy={busyProvider === "outlook"}
            />
        </div>
    );
}
