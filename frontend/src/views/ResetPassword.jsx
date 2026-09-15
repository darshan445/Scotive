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

export default function ResetPasswordPage() {
    const [params] = useSearchParams();
    const token = params.get("token") || "";
    const { resetPassword } = useAuth();
    const router = useRouter();

    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");
    const [done, setDone] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        if (!token) {
            setError("Missing reset token. Request a new link.");
            return;
        }
        if (password.length < 8) {
            setError("Password must be at least 8 characters.");
            return;
        }
        if (password !== confirm) {
            setError("Passwords don't match.");
            return;
        }
        setSubmitting(true);
        const res = await resetPassword(token, password);
        setSubmitting(false);
        if (!res.ok) {
            setError(res.error);
            return;
        }
        setDone(true);
        setTimeout(() => router.replace("/login"), 1500);
    }

    return (
        <AuthShell
            eyebrow="Reset password"
            title={done ? "Password updated." : "Choose a new password."}
            subtitle={done ? "Redirecting you to sign in…" : "Make it something you'll remember."}
            footer={
                <span>
                    <Link href="/login" className="text-foreground font-semibold underline underline-offset-4 hover:text-accent" data-testid="link-back-to-login">
                        Back to sign in
                    </Link>
                </span>
            }
        >
            {done ? (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-800" data-testid="reset-success">
                    Your password has been reset.
                </div>
            ) : (
                <form onSubmit={onSubmit} className="space-y-5" data-testid="reset-form">
                    <div className="space-y-2">
                        <Label htmlFor="password">New password</Label>
                        <Input
                            id="password"
                            type="password"
                            required
                            minLength={8}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="At least 8 characters"
                            className="h-12 rounded-md border-border bg-card text-base"
                            data-testid="reset-password-input"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="confirm">Confirm password</Label>
                        <Input
                            id="confirm"
                            type="password"
                            required
                            minLength={8}
                            value={confirm}
                            onChange={(e) => setConfirm(e.target.value)}
                            placeholder="Same again"
                            className="h-12 rounded-md border-border bg-card text-base"
                            data-testid="reset-confirm-input"
                        />
                    </div>

                    {error ? (
                        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert" data-testid="reset-error">
                            {error}
                        </div>
                    ) : null}

                    <Button
                        type="submit"
                        disabled={submitting}
                        className="w-full h-12 rounded-full font-semibold text-base group"
                        data-testid="reset-submit-button"
                    >
                        {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Update password
                        <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover:translate-x-0.5" />
                    </Button>
                </form>
            )}
        </AuthShell>
    );
}
