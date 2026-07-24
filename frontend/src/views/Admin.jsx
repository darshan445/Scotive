"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, LogOut, RefreshCw } from "lucide-react";
import { api, extractError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function StatCard({ label, value }) {
    return (
        <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 type-title text-2xl tabular-nums">{value}</div>
        </div>
    );
}

function ConnPill({ ok, label }) {
    return (
        <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                ok
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-muted text-muted-foreground border border-border"
            }`}
        >
            {label}
        </span>
    );
}

function formatDate(value) {
    if (!value) return "—";
    try {
        return new Date(value).toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
        });
    } catch {
        return "—";
    }
}

function AdminLogin({ onLoggedIn }) {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function onSubmit(e) {
        e.preventDefault();
        setError("");
        setSubmitting(true);
        try {
            const { data } = await api.post("/admin/login", { email, password });
            onLoggedIn(data);
        } catch (err) {
            setError(extractError(err));
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4">
            <div className="w-full max-w-sm">
                <div className="eyebrow mb-3">Admin</div>
                <h1 className="type-display text-3xl">Scotive ops</h1>
                <p className="type-body mt-2 text-sm text-muted-foreground">
                    Sign in with your admin email and password.
                </p>
                <form onSubmit={onSubmit} className="mt-8 space-y-4" data-testid="admin-login-form">
                    <div className="space-y-2">
                        <Label htmlFor="admin-email">Email</Label>
                        <Input
                            id="admin-email"
                            type="email"
                            autoComplete="username"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            data-testid="admin-email"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="admin-password">Password</Label>
                        <Input
                            id="admin-password"
                            type="password"
                            autoComplete="current-password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            data-testid="admin-password"
                        />
                    </div>
                    {error ? (
                        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                            {error}
                        </div>
                    ) : null}
                    <Button type="submit" className="w-full" disabled={submitting} data-testid="admin-login-submit">
                        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Sign in"}
                    </Button>
                </form>
            </div>
        </div>
    );
}

function AdminDashboard({ admin, onLogout }) {
    const [dashboard, setDashboard] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState("all");

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const { data } = await api.get("/admin/dashboard");
            setDashboard(data);
        } catch (err) {
            setError(extractError(err));
            setDashboard(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const rows = useMemo(() => {
        const users = dashboard?.users || [];
        if (filter === "gmail") return users.filter((u) => u.gmail_connected && !u.qbo_connected);
        if (filter === "qbo") return users.filter((u) => u.qbo_connected && !u.gmail_connected);
        if (filter === "both") return users.filter((u) => u.gmail_connected && u.qbo_connected);
        if (filter === "neither") return users.filter((u) => !u.gmail_connected && !u.qbo_connected);
        return users;
    }, [dashboard, filter]);

    const stats = dashboard?.stats;

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="admin-dashboard">
            <header className="border-b border-border">
                <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
                    <div>
                        <div className="type-title text-base">Admin</div>
                        <div className="text-xs text-muted-foreground">{admin?.email}</div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
                            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
                            Refresh
                        </Button>
                        <Button variant="ghost" size="sm" onClick={onLogout} data-testid="admin-logout">
                            <LogOut className="w-3.5 h-3.5 mr-1.5" />
                            Log out
                        </Button>
                    </div>
                </div>
            </header>

            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-8">
                {error ? (
                    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
                ) : null}

                {stats ? (
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                        <StatCard label="Users" value={stats.total_users} />
                        <StatCard label="Gmail" value={stats.gmail_connected} />
                        <StatCard label="QBO" value={stats.qbo_connected} />
                        <StatCard label="Both" value={stats.both_connected} />
                        <StatCard label="Neither" value={stats.neither_connected} />
                        <StatCard label="Invoices" value={stats.total_invoices} />
                    </div>
                ) : null}

                <div className="flex flex-wrap gap-2">
                    {[
                        { id: "all", label: "All" },
                        { id: "gmail", label: "Gmail only" },
                        { id: "qbo", label: "QBO only" },
                        { id: "both", label: "Both" },
                        { id: "neither", label: "Neither" },
                    ].map((f) => (
                        <button
                            key={f.id}
                            type="button"
                            onClick={() => setFilter(f.id)}
                            className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                                filter === f.id
                                    ? "bg-primary text-primary-foreground border-primary"
                                    : "bg-background text-muted-foreground border-border hover:text-foreground"
                            }`}
                        >
                            {f.label}
                        </button>
                    ))}
                </div>

                <div className="rounded-xl border border-border overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                                <tr>
                                    <th className="px-4 py-3 font-medium">User</th>
                                    <th className="px-4 py-3 font-medium">Joined</th>
                                    <th className="px-4 py-3 font-medium">Connections</th>
                                    <th className="px-4 py-3 font-medium text-right">Invoices</th>
                                    <th className="px-4 py-3 font-medium text-right">Open</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {loading && !dashboard ? (
                                    <tr>
                                        <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                                            <Loader2 className="w-5 h-5 animate-spin inline-block" />
                                        </td>
                                    </tr>
                                ) : rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                                            No users match this filter.
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((u) => (
                                        <tr key={u.id} className="hover:bg-muted/30">
                                            <td className="px-4 py-3">
                                                <div className="font-medium text-foreground">{u.email}</div>
                                                {u.name ? (
                                                    <div className="text-xs text-muted-foreground">{u.name}</div>
                                                ) : null}
                                            </td>
                                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                                                {formatDate(u.created_at)}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex flex-wrap gap-1.5">
                                                    <ConnPill
                                                        ok={u.gmail_connected}
                                                        label={u.gmail_connected ? `Gmail · ${u.gmail_email || "on"}` : "Gmail · off"}
                                                    />
                                                    <ConnPill
                                                        ok={u.qbo_connected}
                                                        label={u.qbo_connected ? `QBO · ${u.qbo_company || "on"}` : "QBO · off"}
                                                    />
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-right tabular-nums font-medium">{u.invoice_count}</td>
                                            <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{u.open_invoice_count}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main>
        </div>
    );
}

export default function AdminPage() {
    const [admin, setAdmin] = useState(null);
    const [checking, setChecking] = useState(true);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const { data } = await api.get("/admin/me");
                if (!cancelled) setAdmin(data);
            } catch {
                if (!cancelled) setAdmin(null);
            } finally {
                if (!cancelled) setChecking(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    async function logout() {
        try {
            await api.post("/admin/logout");
        } catch {
            /* ignore */
        }
        setAdmin(null);
    }

    if (checking) {
        return (
            <div className="min-h-screen flex items-center justify-center text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin" />
            </div>
        );
    }

    if (!admin) {
        return <AdminLogin onLoggedIn={setAdmin} />;
    }

    return <AdminDashboard admin={admin} onLogout={logout} />;
}
