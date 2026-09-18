"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2, Mail } from "lucide-react";
import { MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { api, extractError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const CONTACT_EMAIL = "contact@scotive.com";

export default function ContactPage() {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [company, setCompany] = useState("");
    const [message, setMessage] = useState("");
    const [website, setWebsite] = useState(""); // honeypot
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");
    const [sent, setSent] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        setSubmitting(true);
        try {
            await api.post("/v1/contact", {
                name: name.trim(),
                email: email.trim(),
                company: company.trim() || null,
                message: message.trim(),
                website: website || null,
            });
            setSent(true);
            setName("");
            setEmail("");
            setCompany("");
            setMessage("");
        } catch (err) {
            setError(extractError(err));
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <MarketingShell testId="contact-page" activePath="/contact">
            <MarketingHero
                eyebrow="Contact"
                title="Contact"
                description="You already invoiced them. Scotive watches the thread and the open invoice, and handles the next chase. Email contact@scotive.com."
            />
            <section className="py-12 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="rounded-xl border border-border bg-card px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                    <div className="flex items-center gap-2 text-foreground">
                        <Mail className="w-4 h-4 text-primary shrink-0" />
                        <span className="text-sm font-medium">Email</span>
                    </div>
                    <a
                        href={`mailto:${CONTACT_EMAIL}`}
                        className="text-sm sm:text-base font-medium text-primary hover:underline underline-offset-2"
                        data-testid="contact-email-link"
                    >
                        {CONTACT_EMAIL}
                    </a>
                    <span className="text-xs text-muted-foreground sm:ml-auto">
                        Prefer email? Write us directly.
                    </span>
                </div>

                <div className="mt-10">
                    <h2 className="type-title text-xl md:text-2xl">Send a message</h2>
                    <p className="type-body mt-2 text-sm text-muted-foreground">
                        You already invoiced them. Scotive watches the thread and the open invoice, and
                        handles the next chase.
                    </p>

                    {sent ? (
                        <div
                            className="mt-8 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-6"
                            data-testid="contact-success"
                        >
                            <div className="flex items-start gap-3">
                                <CheckCircle2 className="w-5 h-5 text-emerald-700 mt-0.5 shrink-0" />
                                <div>
                                    <div className="font-medium text-emerald-900">Message sent</div>
                                    <p className="mt-1 text-sm text-emerald-800">
                                        Thanks — we&apos;ll get back to you at the email you provided.
                                        You can also reach us anytime at{" "}
                                        <a
                                            href={`mailto:${CONTACT_EMAIL}`}
                                            className="underline underline-offset-2"
                                        >
                                            {CONTACT_EMAIL}
                                        </a>
                                        .
                                    </p>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="mt-4"
                                        onClick={() => setSent(false)}
                                    >
                                        Send another
                                    </Button>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <form
                            onSubmit={onSubmit}
                            className="mt-8 space-y-5"
                            data-testid="contact-form"
                        >
                            {/* Honeypot — visually hidden from humans */}
                            <div className="absolute -left-[9999px] opacity-0 h-0 w-0 overflow-hidden" aria-hidden>
                                <Label htmlFor="contact-website">Website</Label>
                                <Input
                                    id="contact-website"
                                    name="website"
                                    tabIndex={-1}
                                    autoComplete="off"
                                    value={website}
                                    onChange={(e) => setWebsite(e.target.value)}
                                />
                            </div>

                            <div className="grid gap-5 sm:grid-cols-2">
                                <div className="space-y-2">
                                    <Label htmlFor="contact-name">Name</Label>
                                    <Input
                                        id="contact-name"
                                        name="name"
                                        required
                                        maxLength={120}
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                        placeholder="Your name"
                                        data-testid="contact-name"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="contact-email">Email</Label>
                                    <Input
                                        id="contact-email"
                                        name="email"
                                        type="email"
                                        required
                                        maxLength={200}
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        placeholder="you@company.com"
                                        data-testid="contact-email"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="contact-company">
                                    Company <span className="text-muted-foreground font-normal">(optional)</span>
                                </Label>
                                <Input
                                    id="contact-company"
                                    name="company"
                                    maxLength={200}
                                    value={company}
                                    onChange={(e) => setCompany(e.target.value)}
                                    placeholder="Studio, agency, or team"
                                    data-testid="contact-company"
                                />
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="contact-message">Message</Label>
                                <Textarea
                                    id="contact-message"
                                    name="message"
                                    required
                                    maxLength={5000}
                                    rows={6}
                                    value={message}
                                    onChange={(e) => setMessage(e.target.value)}
                                    placeholder="What are you looking for help with?"
                                    className="min-h-[140px] resize-y"
                                    data-testid="contact-message"
                                />
                            </div>

                            {error ? (
                                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                                    {error}
                                </div>
                            ) : null}

                            <div className="flex flex-wrap items-center gap-3">
                                <Button
                                    type="submit"
                                    disabled={submitting}
                                    data-testid="contact-submit"
                                >
                                    {submitting ? (
                                        <>
                                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                            Sending…
                                        </>
                                    ) : (
                                        "Send message"
                                    )}
                                </Button>
                                <span className="text-xs text-muted-foreground">
                                    Or email{" "}
                                    <a
                                        href={`mailto:${CONTACT_EMAIL}`}
                                        className="text-foreground underline underline-offset-2"
                                    >
                                        {CONTACT_EMAIL}
                                    </a>
                                </span>
                            </div>
                        </form>
                    )}
                </div>

                <p className="mt-12 type-body text-sm text-muted-foreground">
                    Ready to try Scotive?{" "}
                    <Link href="/register" className="text-foreground underline underline-offset-2">
                        Start 30-day free trial
                    </Link>{" "}
                    or read{" "}
                    <Link
                        href="/invoice-reminder-software"
                        className="text-foreground underline underline-offset-2"
                    >
                        Invoice reminder software
                    </Link>
                    .
                </p>
            </section>
        </MarketingShell>
    );
}
