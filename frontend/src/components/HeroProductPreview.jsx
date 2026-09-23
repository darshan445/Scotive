"use client";

import { useState } from "react";

const ROWS = [
    {
        name: "Acme Studio",
        ref: "INV-2041",
        amount: "$2,400",
        status: "Firm to approve",
        statusTone: "danger",
        note: "Still unpaid after Friendly",
        action: "Approve",
        draftTo: "Sarah at Acme",
        draft:
            "Hi Sarah — following up on INV-2041 ($2,400). You mentioned paying last Friday. Here’s the link when you’re ready.",
        pay: true,
    },
    {
        name: "Meraki Co.",
        ref: "INV-2044",
        amount: "$1,850",
        status: "Check back Friday",
        statusTone: "wait",
        note: "Watching until 19 Sep",
        action: "Waiting",
        draftTo: "Alex at Meraki",
        draft:
            "Friendly is on hold. Scotive will surface this again on Friday — no chase while you wait to check back.",
        pay: false,
    },
    {
        name: "Northwind",
        ref: "FS-413",
        amount: "$3,200",
        status: "They replied",
        statusTone: "info",
        note: "Friendly paused",
        action: "Reply",
        draftTo: "Priya at Northwind",
        draft:
            "Hi Priya — thanks for the note on the PO. Here’s the missing line so AP can process FS-413 ($3,200).",
        pay: true,
    },
    {
        name: "Juliet Studio",
        ref: "INV-2038",
        amount: "$2,200",
        status: "Paid",
        statusTone: "ok",
        note: "Cleared yesterday",
        action: "Done",
        draftTo: "Juliet Studio",
        draft: "This invoice is paid in the books. The chase is off — no more follow-ups.",
        pay: false,
    },
];

const TONE = {
    danger: "bg-red-50 text-red-700 border-red-200",
    wait: "bg-amber-50 text-amber-800 border-amber-200",
    info: "bg-sky-50 text-sky-800 border-sky-200",
    ok: "bg-emerald-50 text-emerald-800 border-emerald-200",
};

export function HeroProductPreview() {
    const [selected, setSelected] = useState(0);
    const row = ROWS[selected];

    return (
        <div
            className="rounded-2xl border border-border bg-card shadow-xl shadow-foreground/5 overflow-hidden"
            data-testid="landing-preview-card"
            role="img"
            aria-label="Scotive invoice list with a follow-up draft for the selected client"
        >
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-muted/40">
                <span className="flex gap-1.5" aria-hidden>
                    <span className="h-2.5 w-2.5 rounded-full bg-border" />
                    <span className="h-2.5 w-2.5 rounded-full bg-border" />
                    <span className="h-2.5 w-2.5 rounded-full bg-border" />
                </span>
                <span className="text-xs font-medium text-muted-foreground ml-2">Invoices</span>
                <span className="ml-auto text-[11px] text-muted-foreground">3 need you · $7,450 open</span>
            </div>

            <div className="grid md:grid-cols-[minmax(0,1.15fr)_minmax(0,0.95fr)]">
                <div className="min-w-0">
                    <div className="flex gap-1 px-3 pt-3 pb-2">
                        {["Needs you", "Watching", "Paid"].map((tab, i) => (
                            <span
                                key={tab}
                                className={`rounded-full px-3 py-1 text-[11px] font-medium ${
                                    i === 0 ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                                }`}
                            >
                                {tab}
                                {i === 0 ? " · 3" : ""}
                            </span>
                        ))}
                    </div>
                    <ul>
                        {ROWS.map((item, index) => {
                            const active = index === selected;
                            return (
                                <li key={item.ref}>
                                    <button
                                        type="button"
                                        onClick={() => setSelected(index)}
                                        className={`w-full text-left px-4 py-3 border-t border-border flex items-start gap-3 transition-colors ${
                                            active ? "bg-primary/[0.06]" : "hover:bg-muted/50"
                                        }`}
                                    >
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-baseline justify-between gap-2">
                                                <span className="text-sm font-semibold text-foreground truncate">
                                                    {item.name}
                                                </span>
                                                <span className="text-sm tabular-nums font-medium flex-shrink-0">
                                                    {item.amount}
                                                </span>
                                            </div>
                                            <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                                <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium ${TONE[item.statusTone]}`}>
                                                    {item.status}
                                                </span>
                                                <span className="text-[11px] text-muted-foreground">{item.note}</span>
                                            </div>
                                        </div>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </div>

                <div className="border-t md:border-t-0 md:border-l border-border bg-muted/20 p-4 flex flex-col gap-3 min-h-[280px]">
                    <div className="flex items-start justify-between gap-2">
                        <div>
                            <div className="text-sm font-semibold text-foreground">{row.action} · {row.draftTo}</div>
                            <div className="text-[11px] text-muted-foreground mt-0.5">
                                {row.ref} · {row.amount}
                            </div>
                        </div>
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium ${TONE[row.statusTone]}`}>
                            {row.status}
                        </span>
                    </div>
                    <div className="flex-1 rounded-lg border border-border bg-card px-3 py-3 text-[13px] leading-relaxed text-foreground/85">
                        {row.draft}
                        {row.pay ? (
                            <span className="mt-3 block text-xs font-medium text-primary">Pay invoice →</span>
                        ) : null}
                    </div>
                    <div className="flex gap-2">
                        {row.statusTone === "ok" ? (
                            <span className="flex-1 text-center text-xs font-medium text-muted-foreground border border-border rounded-full py-2">
                                No reminder scheduled
                            </span>
                        ) : row.statusTone === "wait" ? (
                            <span className="flex-1 text-center text-xs font-medium text-muted-foreground border border-border rounded-full py-2">
                                Held until Friday
                            </span>
                        ) : (
                            <>
                                <span className="flex-1 text-center text-xs font-semibold bg-primary text-primary-foreground rounded-full py-2">
                                    Approve &amp; send
                                </span>
                                <span className="text-xs font-medium text-muted-foreground border border-border rounded-full py-2 px-4">
                                    Edit
                                </span>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
