"use client";

import { useCallback, useEffect, useMemo, useState, Fragment } from "react";
import { ChevronDown, ChevronRight, Loader2, LogOut, RefreshCw } from "lucide-react";
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

function formatMoney(amount, currency) {
    if (amount == null || Number.isNaN(Number(amount))) return "—";
    const cur = currency || "USD";
    try {
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency: cur,
            maximumFractionDigits: 2,
        }).format(Number(amount));
    } catch {
        return `${cur} ${Number(amount).toFixed(2)}`;
    }
}

function UserInvoicesPanel({ userId }) {
    const [invoices, setInvoices] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            setLoading(true);
            setError("");
            try {
                const { data } = await api.get(`/admin/users/${userId}/invoices`, {
                    params: { limit: 100 },
                });
                if (!cancelled) setInvoices(data.invoices || []);
            } catch (err) {
                if (!cancelled) {
                    setError(extractError(err));
                    setInvoices([]);
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [userId]);

    if (loading) {
        return (
            <div className="px-4 py-6 text-muted-foreground text-sm flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading invoices…
            </div>
        );
    }
    if (error) {
        return <div className="px-4 py-4 text-sm text-red-700">{error}</div>;
    }
    if (!invoices?.length) {
        return <div className="px-4 py-4 text-sm text-muted-foreground">No invoices for this user.</div>;
    }

    return (
        <div className="px-4 py-3 space-y-3 bg-muted/20 border-t border-border">
            <div className="text-xs font-medium text-muted-foreground">
                Invoices ({invoices.length}) — subject + evidence for fetch QA
            </div>
            <ul className="space-y-3">
                {invoices.map((inv) => (
                    <li
                        key={inv.id}
                        className="rounded-lg border border-border bg-card p-3 text-sm"
                        data-testid="admin-invoice-row"
                    >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <div className="font-medium text-foreground">
                                {inv.invoice_ref || "No ref"} · {formatMoney(inv.amount, inv.currency)}
                            </div>
                            <div className="flex flex-wrap gap-1.5 text-[11px]">
                                <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
                                    {inv.status || "unknown"}
                                </span>
                                {inv.source ? (
                                    <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
                                        {inv.source}
                                    </span>
                                ) : null}
                            </div>
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                            {inv.counterparty_name || inv.counterparty_email || "Unknown client"}
                            {inv.counterparty_name && inv.counterparty_email
                                ? ` · ${inv.counterparty_email}`
                                : ""}
                            {inv.source_date || inv.due_date
                                ? ` · sent ${inv.source_date || "—"} · due ${inv.due_date || "—"}`
                                : ""}
                        </div>
                        <div className="mt-2">
                            <div className="type-label text-muted-foreground">Subject</div>
                            <div className="text-foreground">{inv.source_subject || "—"}</div>
                        </div>
                        <div className="mt-2">
                            <div className="type-label text-muted-foreground">
                                Evidence / snippet
                            </div>
                            <div className="text-muted-foreground whitespace-pre-wrap">
                                {inv.evidence_sentence || "—"}
                            </div>
                        </div>
                    </li>
                ))}
            </ul>
        </div>
    );
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

function ContactInbox({ refreshKey }) {
    const [messages, setMessages] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const { data } = await api.get("/admin/contact-messages", { params: { limit: 50 } });
            setMessages(data.messages || []);
        } catch (err) {
            setError(extractError(err));
            setMessages([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load, refreshKey]);

    async function markRead(id) {
        try {
            await api.post(`/admin/contact-messages/${id}/read`);
            setMessages((prev) =>
                (prev || []).map((m) => (m.id === id ? { ...m, status: "read" } : m))
            );
        } catch {
            /* ignore */
        }
    }

    return (
        <div className="rounded-xl border border-border overflow-hidden" data-testid="admin-contact-inbox">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3">
                <div>
                    <div className="type-title text-sm">Contact inbox</div>
                    <div className="text-xs text-muted-foreground">Messages from /contact</div>
                </div>
                <Button variant="outline" size="sm" onClick={load} disabled={loading}>
                    <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>
            {error ? (
                <div className="px-4 py-3 text-sm text-red-700">{error}</div>
            ) : null}
            {loading && !messages ? (
                <div className="px-4 py-8 text-center text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin inline-block" />
                </div>
            ) : !messages?.length ? (
                <div className="px-4 py-8 text-sm text-muted-foreground text-center">
                    No contact messages yet.
                </div>
            ) : (
                <ul className="divide-y divide-border max-h-[28rem] overflow-y-auto">
                    {messages.map((m) => (
                        <li key={m.id} className="px-4 py-3 text-sm">
                            <div className="flex flex-wrap items-baseline justify-between gap-2">
                                <div className="font-medium text-foreground">
                                    {m.name}
                                    {m.company ? (
                                        <span className="text-muted-foreground font-normal">
                                            {" "}
                                            · {m.company}
                                        </span>
                                    ) : null}
                                </div>
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <span>{formatDate(m.created_at)}</span>
                                    {m.status === "new" ? (
                                        <button
                                            type="button"
                                            onClick={() => markRead(m.id)}
                                            className="rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 hover:bg-emerald-100"
                                        >
                                            Mark read
                                        </button>
                                    ) : (
                                        <span className="rounded-full bg-muted px-2 py-0.5">read</span>
                                    )}
                                </div>
                            </div>
                            <a
                                href={`mailto:${m.email}`}
                                className="text-xs text-primary hover:underline underline-offset-2"
                            >
                                {m.email}
                            </a>
                            <p className="mt-2 text-muted-foreground whitespace-pre-wrap">{m.message}</p>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function AdminDashboard({ admin, onLogout }) {
    const [dashboard, setDashboard] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState("all");
    const [expandedId, setExpandedId] = useState(null);
    const [inboxKey, setInboxKey] = useState(0);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const { data } = await api.get("/admin/dashboard");
            setDashboard(data);
            setInboxKey((k) => k + 1);
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

    function toggleExpand(userId) {
        setExpandedId((cur) => (cur === userId ? null : userId));
    }

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

                <ContactInbox refreshKey={inboxKey} />

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
                                    <th className="px-4 py-3 font-medium w-8" />
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
                                        <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                                            <Loader2 className="w-5 h-5 animate-spin inline-block" />
                                        </td>
                                    </tr>
                                ) : rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                                            No users match this filter.
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((u) => {
                                        const open = expandedId === u.id;
                                        return (
                                            <Fragment key={u.id}>
                                                <tr
                                                    className="hover:bg-muted/30 cursor-pointer"
                                                    onClick={() => toggleExpand(u.id)}
                                                    data-testid={`admin-user-row-${u.id}`}
                                                >
                                                    <td className="px-4 py-3 text-muted-foreground">
                                                        {open ? (
                                                            <ChevronDown className="w-4 h-4" />
                                                        ) : (
                                                            <ChevronRight className="w-4 h-4" />
                                                        )}
                                                    </td>
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
                                                                label={
                                                                    u.gmail_connected
                                                                        ? `Gmail · ${u.gmail_email || "on"}`
                                                                        : "Gmail · off"
                                                                }
                                                            />
                                                            <ConnPill
                                                                ok={u.qbo_connected}
                                                                label={
                                                                    u.qbo_connected
                                                                        ? `QBO · ${u.qbo_company || "on"}`
                                                                        : "QBO · off"
                                                                }
                                                            />
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3 text-right tabular-nums font-medium">
                                                        {u.invoice_count}
                                                    </td>
                                                    <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                                                        {u.open_invoice_count}
                                                    </td>
                                                </tr>
                                                {open ? (
                                                    <tr>
                                                        <td colSpan={6} className="p-0">
                                                            <UserInvoicesPanel userId={u.id} />
                                                        </td>
                                                    </tr>
                                                ) : null}
                                            </Fragment>
                                        );
                                    })
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
