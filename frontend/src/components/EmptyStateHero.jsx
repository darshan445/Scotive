import { Check, Lock, Mail, Sparkles } from "lucide-react";
import { FcGoogle } from "react-icons/fc";
import { ConnectGmailButton } from "@/components/ConnectGmailButton";

function HowItWorksStep({ index, title, description, icon: Icon, iconTone = "dark" }) {
    return (
        <div
            className="flex flex-col gap-3 rounded-xl border border-border bg-card p-6 group hover:border-foreground/30 transition-colors"
            data-testid={`how-step-${index}`}
        >
            <div className="flex items-center justify-between">
                <span className={`inline-flex items-center justify-center w-9 h-9 rounded-lg ${iconTone === "dark" ? "bg-foreground text-background" : "bg-card border border-border"}`}>
                    <Icon className="w-4 h-4" strokeWidth={2} />
                </span>
                <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    Step {index}
                </span>
            </div>
            <h3 className="font-heading font-semibold text-lg text-foreground tracking-tight">
                {title}
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
        </div>
    );
}

export function EmptyStateHero() {
    return (
        <>
            <section
                className="pt-20 md:pt-28 pb-16 md:pb-24 grid lg:grid-cols-12 gap-12 items-start"
                data-testid="empty-state-hero"
            >
                <div className="lg:col-span-8 animate-fade-up">
                    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground mb-6">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        No Gmail connected yet
                    </div>

                    <h1
                        className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl leading-[1.02] tracking-tight text-foreground"
                        data-testid="empty-state-headline"
                    >
                        See every dollar<br />
                        clients owe you —<br />
                        <span className="relative inline-block">
                            <span className="relative z-10">in 60 seconds.</span>
                            <span className="absolute inset-x-0 bottom-1 h-3 bg-[hsl(221_83%_53%_/_0.18)] -z-0" aria-hidden />
                        </span>
                    </h1>

                    <p
                        className="mt-6 text-lg md:text-xl text-muted-foreground leading-relaxed max-w-2xl"
                        data-testid="empty-state-subhead"
                    >
                        {`Scotive reads your Gmail, finds every unpaid invoice, tracks every "I'll pay Friday," and drafts the follow-ups. Nothing is ever sent without your approval.`}
                    </p>

                    <div className="mt-10 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                        <ConnectGmailButton />
                        <div className="text-xs text-muted-foreground max-w-sm leading-relaxed" data-testid="trust-line">
                            Read + send-with-approval access only ·{" "}
                            <span className="text-foreground font-medium">Your emails never train AI models</span> · Disconnect anytime.
                        </div>
                    </div>

                    <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1.5">
                            <Lock className="w-3.5 h-3.5" strokeWidth={2} />
                            Only 2 Gmail permissions
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <Check className="w-3.5 h-3.5" strokeWidth={2} />
                            SOC 2-grade encryption at rest
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <Mail className="w-3.5 h-3.5" strokeWidth={2} />
                            Sends from your own address
                        </span>
                    </div>
                </div>

                <aside
                    className="lg:col-span-4 lg:mt-2 animate-fade-up"
                    style={{ animationDelay: "120ms" }}
                    data-testid="ledger-preview-card"
                >
                    <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-sm">
                        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                            <div className="flex flex-col leading-tight">
                                <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Preview</span>
                                <span className="font-heading font-semibold text-base">You&apos;re owed</span>
                            </div>
                            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                                <Sparkles className="w-3 h-3" />
                                Sample
                            </span>
                        </div>
                        <div className="px-5 py-6">
                            <div className="font-heading font-black text-4xl md:text-5xl tracking-tight tabular-nums">$18,450</div>
                            <div className="mt-1 text-sm text-muted-foreground">across 7 clients</div>
                        </div>
                        <ul className="divide-y divide-border">
                            {[
                                { name: "Northbeam Studio", amount: "$6,200", tag: "Overdue 8d", tone: "red" },
                                { name: "Rahul (Loomcraft)", amount: "$5,000", tag: "Promised Jun 22", tone: "amber" },
                                { name: "Ferra Coffee Co.", amount: "$3,750", tag: "Due tomorrow", tone: "slate" },
                                { name: "Halcyon Legal", amount: "$3,500", tag: "Partial · $500", tone: "green" },
                            ].map((row) => (
                                <li key={row.name} className="px-5 py-3 flex items-center justify-between gap-3">
                                    <div className="flex flex-col min-w-0">
                                        <span className="text-sm font-medium truncate">{row.name}</span>
                                        <span className={`text-[11px] font-mono ${
                                            row.tone === "red" ? "text-red-700" :
                                            row.tone === "amber" ? "text-amber-700" :
                                            row.tone === "green" ? "text-emerald-700" :
                                            "text-muted-foreground"
                                        }`}>
                                            {row.tag}
                                        </span>
                                    </div>
                                    <span className="font-mono text-sm tabular-nums text-foreground">{row.amount}</span>
                                </li>
                            ))}
                        </ul>
                        <div className="px-5 py-3 border-t border-border text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground text-center">
                            Yours will fill in after you connect
                        </div>
                    </div>
                </aside>
            </section>

            <section className="pb-24" data-testid="how-it-works">
                <div className="flex items-baseline justify-between mb-8">
                    <h2 className="font-heading font-bold text-2xl md:text-3xl tracking-tight">How it works</h2>
                    <span className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                        3 steps · ~60 seconds
                    </span>
                </div>
                <div className="grid md:grid-cols-3 gap-4">
                    <HowItWorksStep
                        index={1}
                        title="Connect Gmail"
                        description="Grant read + send-with-approval access. Only two permissions, nothing broader. Revoke any time."
                        icon={FcGoogle}
                        iconTone="light"
                    />
                    <HowItWorksStep
                        index={2}
                        title="We build your money ledger"
                        description="Scotive scans the last 12 months, filters out newsletters and noise, and surfaces every unpaid invoice with the evidence."
                        icon={Sparkles}
                    />
                    <HowItWorksStep
                        index={3}
                        title="You approve & send chasers"
                        description="Every chase draft is written in your voice. Edit, regenerate, or skip. Nothing is ever auto-sent."
                        icon={Check}
                    />
                </div>
            </section>
        </>
    );
}
