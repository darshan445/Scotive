import { Loader2, Mail } from "lucide-react";

const PHASE_COPY = {
    fetching: "Fetching sent mail from the last 90 days…",
    filtering: "Filtering out promos, ads, and unrelated mail…",
    enriching: "Reading invoice PDF attachments…",
    ai: "Reading threads and client replies, identifying invoices…",
};

export function SeedScanProgress({ scanPhase, counts }) {
    const detail = PHASE_COPY[scanPhase] || PHASE_COPY.ai;
    const kept = counts?.kept;
    const candidates = counts?.candidates;

    return (
        <div className="rounded-2xl border border-border bg-card p-8 md:p-10" data-testid="seed-scan-progress">
            <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                    <Mail className="w-5 h-5 text-muted-foreground" />
                </div>
                <div>
                    <div className="eyebrow">First setup</div>
                    <h2 className="type-title text-xl">Finding invoices you sent</h2>
                </div>
            </div>
            <p className="text-sm text-muted-foreground max-w-lg">
                Scanning <span className="font-medium text-foreground">sent mail only</span> — cheap filters first, then AI reads subjects, bodies, and invoice PDFs to find real client invoices. No inbox archaeology.
            </p>
            <div className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                {detail}
            </div>
            {typeof kept === "number" && kept > 0 && scanPhase === "ai" ? (
                <p className="mt-2 text-[11px] font-mono text-muted-foreground">
                    {kept} message{kept === 1 ? "" : "s"} passed filters
                    {typeof candidates === "number" && candidates > 0 ? ` · ${candidates} invoice${candidates === 1 ? "" : "s"} found` : ""}
                </p>
            ) : null}
        </div>
    );
}
