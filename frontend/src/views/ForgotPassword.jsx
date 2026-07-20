"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Loader2 } from "lucide-react";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function ForgotPasswordPage() {
    const { forgotPassword } = useAuth();
    const [email, setEmail] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState("");

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        setSubmitting(true);
        const res = await forgotPassword(email);
        setSubmitting(false);
        if (!res.ok) {
            setError(res.error);
            return;
        }
        setSent(true);
    }

    return (
        <AuthShell
            eyebrow="Reset password"
            title={sent ? "Check your inbox." : "Forgot your password?"}
            subtitle={
                sent
                    ? "If an account exists for that email, a reset link is on its way. It expires in 60 minutes."
                    : `Enter your email and we'll send you a reset link.`
            }
            footer={
                <span>
                    Remembered it?{" "}
                    <Link href="/login" className="text-foreground font-semibold underline underline-offset-4 hover:text-accent" data-testid="link-back-to-login">
                        Back to sign in
                    </Link>
                </span>
            }
        >
            {sent ? (
                <div
                    className="rounded-md border border-border bg-card p-5 text-sm text-muted-foreground"
                    data-testid="forgot-sent-message"
                >
                    We've sent a reset link to <span className="font-mono text-foreground">{email}</span>. Follow the link in that email to choose a new password.
                </div>
            ) : (
                <form onSubmit={onSubmit} className="space-y-5" data-testid="forgot-form">
                    <div className="space-y-2">
                        <Label htmlFor="email" className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                            Work email
                        </Label>
                        <Input
                            id="email"
                            type="email"
                            autoComplete="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="you@company.com"
                            className="h-12 rounded-md border-border bg-card text-base"
                            data-testid="forgot-email-input"
                        />
                    </div>

                    {error ? (
                        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert" data-testid="forgot-error">
                            {error}
                        </div>
                    ) : null}

                    <Button
                        type="submit"
                        disabled={submitting}
                        className="w-full h-12 rounded-md bg-foreground text-background hover:bg-foreground/90 font-semibold text-base group"
                        data-testid="forgot-submit-button"
                    >
                        {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Send reset link
                        <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover:translate-x-0.5" />
                    </Button>
                </form>
            )}
        </AuthShell>
    );
}
