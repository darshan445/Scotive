import { useCallback, useEffect, useState } from "react";
import { Bell, Loader2, Pencil, RefreshCw, Send, X } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { api, extractError } from "@/lib/api";
import { formatMoney } from "@/components/LedgerCard";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

const STEP_LABEL_UI = {
    pre_due_nudge: "Pre-due nudge",
    due_reminder: "Due-date reminder",
    firm_followup: "Firm follow-up",
    final_notice: "Final notice",
    promise_broken: "Broken promise",
};

/**
 * Queue of scheduler-generated chase drafts that need user approval.
 * Nothing is ever sent without an explicit Send click.
 */
export function ChaseQueueCard({ onSent }) {
    const [drafts, setDrafts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/chase-drafts?status=queued");
            setDrafts(data?.drafts || []);
        } catch (e) {
            /* silent — card renders empty */
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    useWorkspaceRefreshEffect(refresh);

    async function runNow() {
        setRunning(true);
        try {
            const { data } = await api.post("/escalation/run");
            if (data.drafts_generated > 0) {
                toast.success(`Generated ${data.drafts_generated} chase draft${data.drafts_generated === 1 ? "" : "s"}`);
            } else {
                toast.info("No new chase drafts today");
            }
            await refresh();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setRunning(false);
        }
    }

    if (loading || drafts.length === 0) {
        // Silent when nothing queued — avoids clutter on the dashboard
        return null;
    }

    return (
        <section data-testid="chase-queue-card">
            <div className="flex items-center justify-between mb-3">
                <h2 className="font-heading font-bold text-xl flex items-center gap-2">
                    <Bell className="w-4 h-4" />
                    Ready to send
                    <span className="text-[11px] font-mono text-muted-foreground" data-testid="chase-queue-count">
                        {drafts.length}
                    </span>
                </h2>
                <button
                    onClick={runNow}
                    disabled={running}
                    data-testid="escalation-run-btn"
                    className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest text-muted-foreground hover:text-foreground disabled:opacity-50">
                    <RefreshCw className={`w-3.5 h-3.5 ${running ? "animate-spin" : ""}`} />
                    {running ? "Generating…" : "Regenerate today"}
                </button>
            </div>
            <div className="space-y-3">
                {drafts.map((d) => (
                    <DraftCard key={d._id} draft={d} onChanged={refresh} onSent={onSent} />
                ))}
            </div>
        </section>
    );
}

function DraftCard({ draft, onChanged, onSent }) {
    const [editing, setEditing] = useState(false);
    const [subject, setSubject] = useState(draft.subject || "");
    const [body, setBody] = useState(draft.body || "");
    const [busy, setBusy] = useState(false);

    async function save() {
        setBusy(true);
        try {
            await api.patch(`/chase-drafts/${draft._id}`, { subject, body });
            toast.success("Draft updated");
            setEditing(false);
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }
    async function regenerate() {
        setBusy(true);
        try {
            const { data } = await api.post(`/chase-drafts/${draft._id}/regenerate`);
            setSubject(data.subject || "");
            setBody(data.body || "");
            toast.success("Regenerated");
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }
    async function dismiss() {
        setBusy(true);
        try {
            await api.post(`/chase-drafts/${draft._id}/dismiss`);
            toast.success("Dismissed");
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }
    async function send() {
        setBusy(true);
        try {
            // If user was mid-edit, save the edit first
            if (editing) {
                await api.patch(`/chase-drafts/${draft._id}`, { subject, body });
            }
            await api.post(`/chase-drafts/${draft._id}/send`);
            toast.success("Sent from your Gmail");
            await onChanged?.();
            await onSent?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    const label = STEP_LABEL_UI[draft.step_label] || draft.step_label || "Chase";

    return (
        <div className="rounded-xl border border-border bg-card p-4" data-testid="chase-draft-card">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                    <span className="inline-block text-[10px] font-mono uppercase tracking-widest px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
                        {label}
                    </span>
                    <Link
                        to={`/clients/${encodeURIComponent(draft.to || "")}`}
                        className="font-medium hover:underline truncate max-w-[240px]"
                        data-testid="chase-draft-client">
                        {draft.counterparty_name || draft.to}
                    </Link>
                    <span className="text-muted-foreground text-sm">·</span>
                    <span className="font-mono text-sm tabular-nums">
                        {formatMoney(draft.amount, draft.currency)}
                    </span>
                    {draft.invoice_ref ? (
                        <span className="text-[11px] font-mono text-muted-foreground">
                            {draft.invoice_ref}
                        </span>
                    ) : null}
                </div>
            </div>
            <div className="mt-3 space-y-2">
                {editing ? (
                    <>
                        <Input
                            value={subject}
                            onChange={(e) => setSubject(e.target.value)}
                            placeholder="Subject"
                            data-testid="chase-draft-subject-input"
                        />
                        <Textarea
                            value={body}
                            onChange={(e) => setBody(e.target.value)}
                            rows={7}
                            placeholder="Body"
                            data-testid="chase-draft-body-input"
                        />
                    </>
                ) : (
                    <>
                        <div className="font-medium text-sm">{draft.subject}</div>
                        <div className="whitespace-pre-wrap text-sm text-foreground/90">
                            {draft.body}
                        </div>
                    </>
                )}
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                {editing ? (
                    <>
                        <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setSubject(draft.subject || ""); setBody(draft.body || ""); }} disabled={busy}>
                            Cancel edit
                        </Button>
                        <Button variant="outline" size="sm" onClick={save} disabled={busy} data-testid="chase-draft-save">
                            Save
                        </Button>
                    </>
                ) : (
                    <>
                        <Button variant="ghost" size="sm" onClick={dismiss} disabled={busy} data-testid="chase-draft-dismiss">
                            <X className="w-3.5 h-3.5 mr-1" /> Dismiss
                        </Button>
                        <Button variant="ghost" size="sm" onClick={regenerate} disabled={busy} data-testid="chase-draft-regenerate">
                            {busy ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1" />}
                            Regenerate
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={busy} data-testid="chase-draft-edit">
                            <Pencil className="w-3.5 h-3.5 mr-1" /> Edit
                        </Button>
                    </>
                )}
                <Button size="sm" onClick={send} disabled={busy} data-testid="chase-draft-send">
                    <Send className="w-3.5 h-3.5 mr-1" /> Send from Gmail
                </Button>
            </div>
        </div>
    );
}
