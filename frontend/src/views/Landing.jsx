import Link from "next/link";
import {
    AlertTriangle,
    ArrowRight,
    BellRing,
    BookOpen,
    Check,
    Link2,
    Calendar,
    ListChecks,
    Pause,
    PenLine,
    Send,
} from "lucide-react";
import { FaqSection } from "@/components/FaqSection";
import { HeroProductPreview } from "@/components/HeroProductPreview";
import { MarketingShell } from "@/components/MarketingShell";
import { PRICE_AFTER_TRIAL, TRIAL_CTA, TRIAL_LABEL } from "@/lib/site";

function SectionEyebrow({ index, children }) {
    const n = String(index).padStart(2, "0");
    return (
        <div className="flex items-center gap-3 mb-4">
            <span className="inline-flex items-center justify-center min-w-[2.25rem] h-9 px-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold tabular-nums">
                {n}
            </span>
            <span className="text-base md:text-lg font-semibold tracking-tight text-foreground">
                {children}
            </span>
            <span className="hidden sm:block h-px flex-1 max-w-[7rem] bg-border" aria-hidden />
        </div>
    );
}

function GapCard({ title, detail, icon: Icon, tone }) {
    const isSolution = tone === "solution";
    return (
        <div className="surface-card p-6">
            <div className="flex items-center justify-between gap-3 mb-4">
                <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/5 text-primary">
                    <Icon className="w-5 h-5" strokeWidth={2} />
                </span>
                <span
                    className={`inline-flex items-center gap-1 text-[11px] font-semibold rounded-full px-2.5 py-1 ${
                        isSolution ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                    }`}
                >
                    {isSolution ? <Check className="w-3 h-3" strokeWidth={2.5} /> : null}
                    {isSolution ? "Scotive" : "The gap"}
                </span>
            </div>
            <h3 className="type-title text-lg leading-snug">{title}</h3>
            <p className="type-body mt-3 text-sm">{detail}</p>
        </div>
    );
}

const LANDING_FAQS = [
    {
        question: "How does the free trial work?",
        answer:
            `Every account starts with a 30-day free trial. ${PRICE_AFTER_TRIAL}`,
    },
    {
        question: "What happens when a client replies?",
        answer:
            "Friendly reminders stop. The invoice moves to Needs you. You write the next email, then pick a date to check back if they still have not paid. Scotive does not send another ‘just checking in’ on an open conversation.",
    },
    {
        question: "Do I still need QuickBooks, Xero, or FreshBooks?",
        answer:
            "Yes. Those stay the ledger. Scotive sits on top: it matches each open invoice to the Gmail or Outlook thread and runs the follow-up from your address.",
    },
    {
        question: "Will it send firmer emails on its own?",
        answer:
            "Friendly reminders can go out on the schedule you approve. Anything firmer waits for a click.",
    },
];

function StepConnectMock() {
    const rows = [
        { name: "Gmail", status: "Connected", on: true },
        { name: "Outlook", status: "Connected", on: true },
        { name: "QuickBooks Online", status: "Connected", on: true },
        { name: "Xero", status: "Connected", on: true },
        { name: "FreshBooks", status: "Connected", on: true },
    ];
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-foreground">Connect your stack</span>
                <span className="text-muted-foreground">OAuth 2.0</span>
            </div>
            {rows.map((row) => (
                <div key={row.name} className="rounded-lg border border-border bg-card px-3 py-2.5 flex items-center gap-2">
                    <Link2 className={`w-3.5 h-3.5 flex-shrink-0 ${row.on ? "text-primary" : "text-muted-foreground"}`} />
                    <span className="text-xs font-medium truncate min-w-0 text-foreground">{row.name}</span>
                    <span
                        className={`ml-auto flex-shrink-0 text-[10px] font-semibold rounded-full px-2 py-0.5 ${
                            row.on
                                ? "text-primary bg-primary/10"
                                : "text-muted-foreground bg-muted"
                        }`}
                    >
                        {row.status}
                    </span>
                </div>
            ))}
        </div>
    );
}

function StepTodayMock() {
    const items = [
        { name: "Acme Studio", action: "Firm to approve" },
        { name: "Meraki Co.", action: "Check back Monday" },
        { name: "Northwind", action: "They replied" },
    ];
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2">
            <div className="text-xs font-semibold mb-1 text-foreground">Needs you</div>
            {items.map((it) => (
                <div key={it.name} className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2">
                    <span className="text-xs text-foreground truncate">{it.name}</span>
                    <span className="text-[10px] font-semibold text-primary bg-primary/10 rounded-full px-2 py-0.5 flex-shrink-0">
                        {it.action}
                    </span>
                </div>
            ))}
        </div>
    );
}

function StepReplyMock() {
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
            <div className="text-xs font-semibold text-foreground">New reply · Northwind</div>
            <div className="rounded-lg border border-border bg-card px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
                Can you resend the missing PO line so AP can process FS-413?
            </div>
            <div className="flex items-center justify-between text-[10px]">
                <span className="text-muted-foreground">Same invoice</span>
                <span className="font-semibold text-primary bg-primary/10 rounded-full px-2 py-0.5">Needs you</span>
            </div>
        </div>
    );
}

const CHASE_RULES = [
    { name: "Before due", meaning: "A short Friendly heads-up can send from your Gmail or Outlook." },
    { name: "Due date", meaning: "A Friendly check-in can send the day it is due." },
    { name: "A week overdue", meaning: "Another Friendly reminder, same thread, same address." },
    { name: "Firm", meaning: "Scotive drafts it. You read it and click send. Nothing firmer goes out alone." },
    { name: "They replied", meaning: "The ladder stops. Needs you. You write the next email and pick when to check back if still unpaid." },
    { name: "Paid in the books", meaning: "QuickBooks, Xero, or FreshBooks hits $0. The chase ends." },
];

function StepApproveMock() {
    return (
        <div
            className="rounded-xl border border-border bg-background p-4 space-y-2.5"
            role="img"
            aria-label="Follow-up email composer for chasing an unpaid invoice"
        >
            <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-foreground truncate">Follow up with Acme Studio</span>
                <span className="text-[10px] font-medium text-muted-foreground border border-border bg-muted/50 rounded-full px-2 py-0.5 flex-shrink-0">
                    Firm follow-up
                </span>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
                Hi Sarah — following up on INV-2041 ($2,400). You mentioned paying by last Friday…
            </div>
            <div className="flex gap-2">
                <span className="flex-1 text-center text-[11px] font-semibold bg-primary text-primary-foreground rounded-lg py-1.5">Approve &amp; send</span>
                <span className="text-[11px] font-medium text-muted-foreground border border-border rounded-lg py-1.5 px-3">Edit</span>
            </div>
        </div>
    );
}

function HowItWorksStep({ index, title, description, mock }) {
    return (
        <article
            className={`surface-card p-6 lg:p-7 ${
                mock ? "grid lg:grid-cols-[minmax(0,1fr)_minmax(0,17rem)] gap-6 items-start" : ""
            }`}
            data-testid={`landing-how-step-${index}`}
        >
            <div>
                <div className="flex items-center gap-3 mb-3">
                    <span className="inline-flex items-center justify-center min-w-[2rem] h-8 px-2 rounded-md bg-primary/10 text-primary text-xs font-semibold tabular-nums">
                        {String(index).padStart(2, "0")}
                    </span>
                    <span className="h-px flex-1 bg-border" />
                </div>
                <h3 className="type-title text-xl">{title}</h3>
                <p className="type-body mt-2 text-sm">{description}</p>
            </div>
            {mock ? <div className="lg:mt-1">{mock}</div> : null}
        </article>
    );
}

export default function LandingPage() {
    return (
        <MarketingShell testId="landing-page" activePath="/">
                <section
                    className="relative overflow-hidden border-b border-border bg-gradient-to-b from-primary/[0.07] to-background"
                    data-testid="landing-hero"
                >
                    <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 md:pt-24 text-center">
                        <p className="eyebrow mb-4">{TRIAL_LABEL}</p>
                        <h1
                            className="type-display text-4xl sm:text-5xl lg:text-[3.4rem] text-balance"
                            data-testid="landing-headline"
                        >
                            Get paid without the awkward follow-up.
                        </h1>
                        <p
                            className="type-body mt-5 text-base md:text-lg max-w-2xl mx-auto"
                            data-testid="landing-subhead"
                        >
                            Scotive matches each open invoice from QuickBooks, Xero, or FreshBooks to the
                            Gmail or Outlook thread, sends Friendly reminders you approve, and pauses the
                            moment they reply. Firm emails wait for a click.
                        </p>
                        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
                            <Link
                                href="/register"
                                className="btn-pill-primary text-base px-7 py-3"
                                data-testid="landing-cta-primary"
                            >
                                {TRIAL_CTA}
                                <ArrowRight className="w-4 h-4" />
                            </Link>
                            <Link
                                href="/pricing"
                                className="btn-pill-outline text-base px-7 py-3"
                                data-testid="landing-cta-secondary"
                            >
                                View pricing
                            </Link>
                        </div>
                    </div>
                    <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-12 md:pt-16 pb-16 md:pb-24">
                        <HeroProductPreview />
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-pain">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow index={1}>The problem</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Your invoicing tools already send reminders, but they only know the date —
                                and they are dumb.
                            </h2>
                            <p className="type-body mt-3">
                                QuickBooks, Xero, and FreshBooks send reminders on a calendar. They cannot
                                see the Gmail or Outlook thread, so they keep sending after the client already
                                talked — and they never write the next email from your inbox.
                            </p>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <GapCard
                                tone="problem"
                                icon={Calendar}
                                title="A calendar is not context"
                                detail="Day 7 overdue is not the same as “paying Friday,” a question on the PO, or “we already paid.” Date-based reminders treat all of those as the same stamp."
                            />
                            <GapCard
                                tone="problem"
                                icon={PenLine}
                                title="You still have to write the next email"
                                detail="The invoicing tool sends a canned note from its own domain. You are still in Gmail guessing the wording — and waiting weeks because it feels awkward."
                            />
                            <GapCard
                                tone="problem"
                                icon={Pause}
                                title="They do not know when to stop"
                                detail="If the client already replied, the next dated reminder still goes. If they promised a day, you still get “overdue.” You are the one who has to notice and pull it back."
                            />
                            <GapCard
                                tone="problem"
                                icon={ListChecks}
                                title="After they talk, you are the system"
                                detail="A reply, a pay date they named, or “we already paid” is not on the reminder calendar. You rebuild the next chase from sent mail, every week, across a pile of open invoices."
                            />
                        </div>
                        <div className="mt-10 text-center" data-testid="landing-pain-bridge">
                            <p className="type-title text-xl md:text-2xl">
                                Don’t worry. Scotive is built for all four.
                            </p>
                            <Link
                                href="#the-solution"
                                className="btn-pill-primary text-base px-6 py-3 mt-5 inline-flex"
                                data-testid="landing-pain-bridge-cta"
                            >
                                See how it solves them
                                <ArrowRight className="w-4 h-4" />
                            </Link>
                        </div>
                    </div>
                </section>

                <section
                    id="the-solution"
                    className="py-20 md:py-24 border-t border-border/70 scroll-mt-24"
                    data-testid="landing-solution"
                >
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow index={2}>The solution</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Same four gaps. Closed from the thread on that invoice.
                            </h2>
                            <p className="type-body mt-3">
                                Scotive fetches the invoice, matches the Gmail or Outlook thread, sends Friendly
                                reminders you approve, and pauses the moment they reply. Firm emails wait for a click.
                            </p>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <GapCard
                                tone="solution"
                                icon={Calendar}
                                title="The thread is the brake"
                                detail="It reads that invoice’s Gmail or Outlook conversation. A reply, a pay date they named, or “we already paid” is not another overdue stamp — Friendly stops so you are not the one who has to notice."
                            />
                            <GapCard
                                tone="solution"
                                icon={PenLine}
                                title="The next email is already drafted"
                                detail="Friendly reminders go from your address, on the same thread, with a pay link. When they reply, you write the next email — you are not guessing “just checking in” on silence."
                            />
                            <GapCard
                                tone="solution"
                                icon={Pause}
                                title="It knows when to hold"
                                detail="If they replied, Friendly stops. You pick a date to check back if still unpaid. No second reminder on an open conversation. Firm emails still need a click."
                            />
                            <GapCard
                                tone="solution"
                                icon={ListChecks}
                                title="Needs you, Watching, or Paid"
                                detail="Replies and Firm sit in Needs you. A check-back date sits in Watching. Paid in the books ends the chase. You are not reconstructing next steps from sent mail."
                            />
                        </div>
                    </div>
                </section>

                <section id="how-it-works" className="py-20 md:py-24 border-t border-border/70 scroll-mt-24" data-testid="landing-how-it-works">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow index={3}>How it works</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Sign up. Connect. Friendly reminders run. You approve anything firmer.
                            </h2>
                            <p className="type-body mt-3">
                                Scotive pulls invoices from your invoicing tools, keeps the Gmail or Outlook
                                thread on each one in sync, and runs the chase from your inbox.
                            </p>
                        </div>
                        <div className="space-y-4">
                            <HowItWorksStep
                                index={1}
                                title="Connect the inbox and the invoicing tool"
                                description="After you sign up, connect Gmail or Outlook — or both — where clients actually talk. Then connect QuickBooks, Xero, or FreshBooks. Scotive pulls the invoices, then the conversations that belong to them. New mail keeps syncing, so a reply tomorrow is on the same invoice."
                                mock={<StepConnectMock />}
                            />
                            <HowItWorksStep
                                index={2}
                                title="Friendly reminders send while they stay silent"
                                description="You approve the Friendly ladder once. A heads-up before due, a note on the due date, another a week later — from your Gmail or Outlook, on the same thread. Needs you is for replies, Firm drafts, and a check-back date that came due unpaid."
                                mock={<StepTodayMock />}
                            />
                            <HowItWorksStep
                                index={3}
                                title="Firm waits for you"
                                description="After Friendly, Scotive drafts a firmer email. You read it and click send. Nothing firmer goes out alone — a bot that keeps nagging after someone already talked starts to hurt the relationship."
                                mock={<StepApproveMock />}
                            />
                            <HowItWorksStep
                                index={4}
                                title="They reply. The ladder stops."
                                description="A reply lands on that invoice, not in a separate pile. Friendly stops. Needs you. You write the next email and pick a date to check back if they still have not paid. When the books hit $0, the chase ends."
                                mock={<StepReplyMock />}
                            />
                        </div>

                        <div className="mt-14" data-testid="landing-how-statuses">
                            <h3 className="type-title text-2xl md:text-3xl">How the chase runs — and when it stops</h3>
                            <p className="type-body mt-2 max-w-2xl">
                                Friendly reminders follow the due date while they stay silent. The Gmail or Outlook
                                thread is the brake. Paid in QuickBooks, Xero, or FreshBooks ends the chase.
                            </p>
                            <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {CHASE_RULES.map((item) => (
                                    <div key={item.name} className="surface-card p-4">
                                        <div className="text-sm font-semibold text-foreground">{item.name}</div>
                                        <p className="type-body mt-1.5 text-xs">{item.meaning}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-who">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-10">
                            <SectionEyebrow index={4}>Who it’s for</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Built for agencies and consultants who already send invoices.
                            </h2>
                            <p className="type-body mt-3">
                                If you have a pile of open invoices and still follow up from Gmail or Outlook, Scotive is the layer on top of the books you already keep.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {[
                                "Agency owner",
                                "Managing director",
                                "Head of operations",
                                "Studio manager",
                                "Principal consultant",
                            ].map((label) => (
                                <span
                                    key={label}
                                    className="text-sm font-medium text-foreground/80 bg-muted rounded-full px-3.5 py-1.5"
                                >
                                    {label}
                                </span>
                            ))}
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-seo-links">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-10">
                            <SectionEyebrow index={5}>Guides</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Guides
                            </h2>
                        </div>
                        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            {[
                                {
                                    href: "/past-due-invoice-reminder",
                                    icon: BellRing,
                                    title: "Past due invoice reminder",
                                    detail: "I'll pay Friday / promised and didn't / says paid / partial / after they replied.",
                                },
                                {
                                    href: "/invoice-reminder-software",
                                    icon: BookOpen,
                                    title: "Invoice reminder software",
                                    detail: "You already have QBO/Xero. Approved Friendly cadence, pause on reply, pay link, from Gmail/Outlook.",
                                },
                                {
                                    href: "/payment-reminder-email-template",
                                    icon: Send,
                                    title: "Payment reminder email template",
                                    detail: "Softer / pre-due. Invoice #, amount, due date, and a payment link.",
                                },
                                {
                                    href: "/how-to-chase-outstanding-invoices",
                                    icon: AlertTriangle,
                                    title: "How to chase outstanding invoices",
                                    detail: "The buyer who already has QBO/Xero and is still in Gmail writing just checking in.",
                                },
                            ].map((item) => (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className="surface-card p-5 hover:shadow-md transition-shadow block"
                                >
                                    <item.icon className="w-5 h-5 text-primary mb-3" strokeWidth={2} />
                                    <h3 className="type-title text-base">{item.title}</h3>
                                    <p className="type-body mt-1.5 text-sm">{item.detail}</p>
                                </Link>
                            ))}
                        </div>
                    </div>
                </section>

                <FaqSection
                    items={LANDING_FAQS}
                    kicker={<SectionEyebrow index={6}>FAQ</SectionEyebrow>}
                />

                <section className="py-20 md:py-28" data-testid="landing-final-cta">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="rounded-3xl ink-panel px-8 py-14 md:px-16 md:py-20 text-center relative overflow-hidden">
                            <div className="absolute inset-0 dot-grid opacity-40 pointer-events-none" aria-hidden />
                            <div className="relative">
                                <div className="flex justify-center mb-6">
                                    <img src="/scotive-icon.png" alt="Scotive" width={56} height={56} className="w-14 h-14 rounded-2xl" />
                                </div>
                                <h2 className="type-display text-3xl md:text-5xl">
                                    Get paid without the awkward follow-up.
                                </h2>
                                <p className="type-body mt-4 text-base md:text-lg opacity-80 max-w-xl mx-auto">
                                    It matches each open invoice from QuickBooks, Xero, or FreshBooks to the Gmail or Outlook thread, sends Friendly reminders you approve, and pauses the moment they reply. Firm emails wait for a click. {TRIAL_LABEL}. {PRICE_AFTER_TRIAL}
                                </p>
                                <div className="mt-9 flex flex-col sm:flex-row items-center justify-center gap-4">
                                    <Link
                                        href="/register"
                                        className="btn-pill-primary bg-background text-foreground hover:bg-background/90 px-7 py-3.5 text-base"
                                        data-testid="landing-cta-final"
                                    >
                                        {TRIAL_CTA}
                                        <ArrowRight className="w-4 h-4" />
                                    </Link>
                                    <Link href="/pricing" className="btn-pill-outline border-background/30 text-background hover:bg-background/10 px-7 py-3.5 text-base">
                                        View pricing
                                    </Link>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
        </MarketingShell>
    );
}
