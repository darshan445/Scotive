"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
    const { login } = useAuth();
    const router = useRouter();
    const searchParams = useSearchParams();
    const rawNext = searchParams.get("next") || "/dashboard";
    const next = rawNext.startsWith("/") ? rawNext : "/dashboard";

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        setSubmitting(true);
        const res = await login(email, password);
        setSubmitting(false);
        if (!res.ok) {
            setError(res.error);
            return;
        }
        router.replace(next);
    }

    return (
        <AuthShell
            eyebrow="Sign in"
            title="Welcome back."
            subtitle="Pick up where you left off — chase what's owed, approve every send."
            footer={
                <span>
                    New to Scotive?{" "}
                    <Link href="/register" className="text-foreground font-semibold underline underline-offset-4 hover:text-accent" data-testid="link-to-register">
                        Create an account
                    </Link>
                </span>
            }
        >
            <form onSubmit={onSubmit} className="space-y-5" data-testid="login-form">
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
                        data-testid="login-email-input"
                    />
                </div>
                <div className="space-y-2">
                    <div className="flex items-baseline justify-between">
                        <Label htmlFor="password" className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                            Password
                        </Label>
                        <Link
                            href="/forgot-password"
                            className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
                            data-testid="link-to-forgot"
                        >
                            Forgot?
                        </Link>
                    </div>
                    <Input
                        id="password"
                        type="password"
                        autoComplete="current-password"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="h-12 rounded-md border-border bg-card text-base"
                        data-testid="login-password-input"
                    />
                </div>

                {error ? (
                    <div
                        className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                        role="alert"
                        data-testid="login-error"
                    >
                        {error}
                    </div>
                ) : null}

                <Button
                    type="submit"
                    disabled={submitting}
                    className="w-full h-12 rounded-md bg-foreground text-background hover:bg-foreground/90 font-semibold text-base group"
                    data-testid="login-submit-button"
                >
                    {submitting ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : null}
                    Sign in
                    <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover:translate-x-0.5" />
                </Button>
            </form>
        </AuthShell>
    );
}
