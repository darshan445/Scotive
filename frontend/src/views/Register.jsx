"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function RegisterPage() {
    const { register } = useAuth();
    const router = useRouter();

    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        if (password.length < 8) {
            setError("Password must be at least 8 characters.");
            return;
        }
        setSubmitting(true);
        let timezone = null;
        try {
            timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
        } catch {
            timezone = null;
        }
        try {
            const res = await register(email, password, name.trim() || null, timezone);
            if (!res.ok) {
                setError(res.error);
                return;
            }
            router.replace("/dashboard");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <AuthShell
            eyebrow="Create account"
            title="Create your account"
            subtitle="Start a 30-day free trial. No card required."
            footer={
                <span>
                    Already have an account?{" "}
                    <Link href="/login" className="text-foreground font-semibold underline underline-offset-4 hover:text-primary" data-testid="link-to-login">
                        Sign in
                    </Link>
                </span>
            }
        >
            <form onSubmit={onSubmit} className="space-y-5" data-testid="register-form">
                <div className="space-y-2">
                    <Label htmlFor="name">
                        Name <span className="font-normal text-muted-foreground">(optional)</span>
                    </Label>
                    <Input
                        id="name"
                        type="text"
                        autoComplete="name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Alex Rivera"
                        className="h-12 rounded-md border-border bg-card text-base"
                        data-testid="register-name-input"
                    />
                </div>
                <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                        id="email"
                        type="email"
                        autoComplete="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@company.com"
                        className="h-12 rounded-md border-border bg-card text-base"
                        data-testid="register-email-input"
                    />
                </div>
                <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                        id="password"
                        type="password"
                        autoComplete="new-password"
                        required
                        minLength={8}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="At least 8 characters"
                        className="h-12 rounded-md border-border bg-card text-base"
                        data-testid="register-password-input"
                    />
                </div>

                {error ? (
                    <div
                        className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                        role="alert"
                        data-testid="register-error"
                    >
                        {error}
                    </div>
                ) : null}

                <Button
                    type="submit"
                    disabled={submitting}
                    className="w-full h-12 rounded-full font-semibold text-base group"
                    data-testid="register-submit-button"
                >
                    {submitting ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : null}
                    Create account
                    <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover:translate-x-0.5" />
                </Button>

                <p className="text-xs text-muted-foreground leading-relaxed">
                    By creating an account you agree to Scotive&apos;s{" "}
                    <Link href="/terms" className="underline underline-offset-2 hover:text-foreground">
                        Terms
                    </Link>{" "}
                    and{" "}
                    <Link href="/privacy" className="underline underline-offset-2 hover:text-foreground">
                        Privacy Policy
                    </Link>
                    . Your emails are never used to train Scotive&apos;s AI models.
                </p>
            </form>
        </AuthShell>
    );
}
