import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function RegisterPage() {
    const { register } = useAuth();
    const navigate = useNavigate();

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
        const res = await register(email, password, name.trim() || null);
        setSubmitting(false);
        if (!res.ok) {
            setError(res.error);
            return;
        }
        navigate("/dashboard", { replace: true });
    }

    return (
        <AuthShell
            eyebrow="Create account"
            title="Get paid faster, without the awkward chase."
            subtitle="60 seconds to your first ledger. Read + send-with-approval Gmail access only."
            footer={
                <span>
                    Already have an account?{" "}
                    <Link to="/login" className="text-foreground font-semibold underline underline-offset-4 hover:text-accent" data-testid="link-to-login">
                        Sign in
                    </Link>
                </span>
            }
        >
            <form onSubmit={onSubmit} className="space-y-5" data-testid="register-form">
                <div className="space-y-2">
                    <Label htmlFor="name" className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                        Your name <span className="normal-case tracking-normal text-muted-foreground/70">(optional)</span>
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
                        data-testid="register-email-input"
                    />
                </div>
                <div className="space-y-2">
                    <Label htmlFor="password" className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                        Password
                    </Label>
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
                    className="w-full h-12 rounded-md bg-foreground text-background hover:bg-foreground/90 font-semibold text-base group"
                    data-testid="register-submit-button"
                >
                    {submitting ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : null}
                    Create account
                    <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover:translate-x-0.5" />
                </Button>

                <p className="text-xs text-muted-foreground leading-relaxed">
                    {`By creating an account you agree to Scotive's Terms and Privacy policy. Your emails are never used to train AI models.`}
                </p>
            </form>
        </AuthShell>
    );
}
