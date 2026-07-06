import { useState } from "react";
import { GitMerge, X } from "lucide-react";
import { api, extractError } from "@/lib/api";
import { toast } from "sonner";

/**
 * One-tap cross-domain client merge prompts (PRD §6).
 */
export function ClientMergePrompts({ prompts, onChanged }) {
    const rows = prompts || [];
    const [busyId, setBusyId] = useState(null);

    if (!rows.length) return null;

    async function confirm(id) {
        setBusyId(id);
        try {
            await api.post(`/clients/merge-prompts/${id}/confirm`);
            toast.success("Clients merged");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusyId(null);
        }
    }

    async function dismiss(id) {
        setBusyId(id);
        try {
            await api.post(`/clients/merge-prompts/${id}/dismiss`);
            toast.success("Kept separate");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusyId(null);
        }
    }

    return (
        <div className="space-y-3" data-testid="client-merge-prompts">
            {rows.map((p) => (
                <div
                    key={p._id}
                    className="rounded-2xl border border-sky-200 bg-sky-50/40 p-5"
                    data-testid="client-merge-card">
                    <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                            <GitMerge className="w-4 h-4 text-sky-800 shrink-0" />
                            <div className="min-w-0">
                                <div className="font-heading font-semibold text-sm text-sky-950">
                                    Same client?
                                </div>
                                <p className="mt-1 text-xs text-sky-900/80">{p.match_label}</p>
                            </div>
                        </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-mono text-muted-foreground">
                        {(p.emails || []).map((em) => (
                            <span key={em}>{em}</span>
                        ))}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                        <button
                            type="button"
                            onClick={() => confirm(p._id)}
                            disabled={busyId === p._id}
                            data-testid="client-merge-confirm"
                            className="rounded-md bg-sky-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-900 disabled:opacity-50">
                            Merge into one client
                        </button>
                        <button
                            type="button"
                            onClick={() => dismiss(p._id)}
                            disabled={busyId === p._id}
                            data-testid="client-merge-dismiss"
                            className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 disabled:opacity-50">
                            <X className="w-3 h-3" />
                            Not the same
                        </button>
                    </div>
                </div>
            ))}
        </div>
    );
}
