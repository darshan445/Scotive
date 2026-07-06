import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Check, Eye, Lock, Mail, Send, Wallet } from "lucide-react";
import { FcGoogle } from "react-icons/fc";

function HowItWorksStep({ index, title, description, icon: Icon, iconTone = "dark" }) {
    return (
        <div
            className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow"
            data-testid={`landing-how-step-${index}`}
        >
            <div className="flex items-center justify-between">
                <span className={`inline-flex items-center justify-center w-10 h-10 rounded-xl ${iconTone === "dark" ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"}`}>
                    <Icon className="w-4 h-4" strokeWidth={2} />
                </span>
                <span className="pill text-[11px]">
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

export default function LandingPage() {
    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="landing-page">
            <header className="border-b border-border bg-card/80 backdrop-blur-md sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-2 font-heading font-bold text-lg tracking-tight">
                        <span className="w-2 h-2 rounded-full bg-primary" />
                        Scotive
                    </Link>
                    <nav className="flex items-center gap-2 sm:gap-4">
                        <Link
                            to="/login"
                            className="text-sm font-medium px-3 py-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            data-testid="landing-signin"
                        >
                            Sign in
                        </Link>
                        <Link
                            to="/register"
                            className="inline-flex items-center gap-1.5 text-sm font-semibold bg-primary text-primary-foreground px-4 py-2 rounded-full hover:bg-primary/90 transition-colors shadow-sm"
                            data-testid="landing-signup"
                        >
                            Get started
                            <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </nav>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <section
                    className="pt-20 md:pt-28 pb-16 md:pb-24 grid lg:grid-cols-12 gap-12 items-start"
                    data-testid="landing-hero"
                >
                    <div className="lg:col-span-8 animate-fade-up">
                        <div className="pill mb-6">
                            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                            Payment ops inside Gmail
                        </div>

                        <h1
                            className="font-heading font-extrabold text-4xl sm:text-5xl lg:text-[3.5rem] leading-[1.08] tracking-tight text-foreground"
                            data-testid="landing-headline"
                        >
                            Chase every invoice —<br />
                            <span className="text-primary">automatically.</span>
                        </h1>

                        <p
                            className="mt-6 text-lg text-muted-foreground leading-relaxed max-w-2xl"
                            data-testid="landing-subhead"
                        >
                            Scotive watches your Gmail, tracks invoices you send, reads client replies, and drafts the follow-ups. Nothing sends without your approval.
                        </p>

                        <div className="mt-10 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                            <Link
                                to="/register"
                                className="group inline-flex items-center gap-3 rounded-full bg-primary text-primary-foreground pl-2 pr-6 py-2 font-semibold text-base transition-all shadow-md hover:shadow-lg active:scale-[0.98] hover:bg-primary/90"
                                data-testid="landing-cta-primary"
                            >
                                <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-background border border-border">
                                    <FcGoogle className="w-5 h-5" />
                                </span>
                                Get started free
                                <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
                            </Link>
                            <Link
                                to="/login"
                                className="text-sm font-medium text-muted-foreground hover:text-foreground"
                                data-testid="landing-cta-secondary"
                            >
                                Already have an account? Sign in →
                            </Link>
                        </div>

                        <div className="mt-6 text-xs text-muted-foreground max-w-md leading-relaxed" data-testid="landing-trust-line">
                            Read + send-with-approval Gmail access only ·{" "}
                            <span className="text-foreground font-medium">Your emails never train AI models</span> · Disconnect anytime.
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
                        data-testid="landing-preview-card"
                    >
                        <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-md">
                            <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-muted/30">
                                <div className="flex flex-col leading-tight">
                                    <span className="text-xs font-medium text-muted-foreground">Preview</span>
                                    <span className="font-heading font-semibold text-base">Today</span>
                                </div>
                                <span className="pill text-[11px]">Sample</span>
                            </div>
                            <ul className="divide-y divide-border">
                                {[
                                    { icon: AlertTriangle, name: "Acme Studio", amount: "$2,400", tag: "4 days overdue", tone: "red", action: "View follow-up draft" },
                                    { icon: Wallet, name: "Meraki Co.", amount: "$1,850", tag: "Due today", tone: "amber", action: "View reminder draft" },
                                    { icon: Eye, name: "Nuts Over Tech", amount: "₹84,700", tag: "Due Jul 3 — reading replies", tone: "slate", action: null },
                                ].map((row) => (
                                    <li key={row.name} className="px-5 py-3.5">
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="flex gap-2 min-w-0">
                                                <row.icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                                                    row.tone === "red" ? "text-red-600" :
                                                    row.tone === "amber" ? "text-amber-600" :
                                                    "text-muted-foreground"
                                                }`} />
                                                <div className="min-w-0">
                                                    <span className="text-sm font-medium truncate block">{row.name}</span>
                                                    <span className={`text-[11px] font-mono ${
                                                        row.tone === "red" ? "text-red-700" :
                                                        row.tone === "amber" ? "text-amber-700" :
                                                        "text-muted-foreground"
                                                    }`}>
                                                        {row.tag}
                                                    </span>
                                                </div>
                                            </div>
                                            <span className="font-mono text-sm tabular-nums text-foreground flex-shrink-0">{row.amount}</span>
                                        </div>
                                        {row.action ? (
                                            <div className="mt-2 ml-6 text-[11px] font-medium text-foreground/80 inline-flex items-center gap-1">
                                                <Send className="w-3 h-3" /> {row.action}
                                            </div>
                                        ) : null}
                                    </li>
                                ))}
                            </ul>
                            <div className="px-5 py-3 border-t border-border text-xs text-muted-foreground text-center">
                                Yours starts after a 60-second pick-list
                            </div>
                        </div>
                    </aside>
                </section>

                <section className="pb-24" data-testid="landing-how-it-works">
                    <div className="flex items-baseline justify-between mb-8">
                        <h2 className="font-heading font-bold text-2xl md:text-3xl tracking-tight">How it works</h2>
                        <span className="pill text-xs">3 steps · ~60 seconds</span>
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
                            title="Pick what's still unpaid"
                            description="Scotive finds invoices you sent in the last 90 days. You tap which ones to track — you know your recent work cold."
                            icon={Check}
                        />
                        <HowItWorksStep
                            index={3}
                            title="Approve & send chasers"
                            description="Every chase draft is written in your voice. Edit, regenerate, or skip. Nothing is ever auto-sent."
                            icon={Send}
                        />
                    </div>
                </section>

                <section className="pb-24" data-testid="landing-final-cta">
                    <div className="rounded-2xl border border-border bg-card p-8 md:p-12 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 shadow-sm">
                        <div>
                            <h2 className="font-heading font-bold text-2xl md:text-3xl tracking-tight">
                                Send invoices like always. Scotive watches from here.
                            </h2>
                            <p className="mt-2 text-sm text-muted-foreground max-w-xl">
                                Connect in under a minute. Pick your open invoices. Approve your first chase draft before your coffee gets cold.
                            </p>
                        </div>
                        <Link
                            to="/register"
                            className="inline-flex items-center gap-2 rounded-full bg-primary text-primary-foreground px-6 py-3 font-semibold text-base hover:bg-primary/90 transition-colors shadow-md"
                            data-testid="landing-cta-final"
                        >
                            Get started free
                            <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </section>
            </main>

            <footer className="border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-wrap justify-between items-center gap-3 text-sm text-muted-foreground">
                    <span>© {new Date().getFullYear()} Scotive</span>
                    <span>Payment ops · Inside Gmail</span>
                </div>
            </footer>
        </div>
    );
}
