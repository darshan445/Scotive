import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api, extractError } from "@/lib/api";
import { formatTimelineEntry, gmailThreadUrl } from "@/lib/invoiceTimeline";
import { Skeleton } from "@/components/ui/skeleton";

export function InvoiceTimeline({ invoiceId, className = "" }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");

    useEffect(() => {
        let alive = true;
        api.get(`/invoices/${invoiceId}/timeline`)
            .then(({ data: res }) => { if (alive) setData(res); })
            .catch((e) => { if (alive) setErr(extractError(e)); });
        return () => { alive = false; };
    }, [invoiceId]);

    if (err) return <div className="text-sm text-red-700">{err}</div>;
    if (!data) {
        return (
            <div className="space-y-3" data-testid="timeline-skeleton">
                {[0, 1, 2].map((i) => (
                    <div key={i} className="grid grid-cols-[4.5rem_1fr] gap-x-3">
                        <Skeleton className="h-3 w-12" />
                        <Skeleton className="h-4 w-full max-w-xs" />
                    </div>
                ))}
            </div>
        );
    }

    const invoice = data.invoice || {};
    const events = data.events || [];
    if (!events.length) {
        return <div className="text-sm text-muted-foreground">No conversation history yet.</div>;
    }

    return (
        <div className={`text-sm ${className}`} data-testid="invoice-timeline">
            <div className="space-y-2.5">
                {events.map((ev, i) => {
                    const row = formatTimelineEntry(ev, invoice);
                    const link = gmailThreadUrl(row.threadId);
                    return (
                        <div key={ev.message_id || `${ev.kind}-${ev.date}-${i}`} className="grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-0.5">
                            <div className="text-[11px] font-mono text-muted-foreground tabular-nums pt-0.5">{row.day}</div>
                            <div className="min-w-0">
                                <div className="text-foreground leading-snug">{row.body}</div>
                                {link ? (
                                    <a
                                        href={link}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                                        data-testid="timeline-view-email">
                                        View full email
                                        <ExternalLink className="w-3 h-3" />
                                    </a>
                                ) : null}
                            </div>
                        </div>
                    );
                })}
            </div>
            {data.next ? (
                <>
                    <div className="my-3 border-t border-border/80" />
                    <div className="text-[11px] font-mono text-muted-foreground" data-testid="timeline-next">
                        Next: {data.next}
                    </div>
                </>
            ) : null}
        </div>
    );
}
