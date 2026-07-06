import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Loader2, Save, Trash2 } from "lucide-react";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { api, extractError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ConnectionPanel } from "@/components/ConnectionPanel";
import { useGmailConnection } from "@/hooks/useGmailConnection";

const ESCALATION_LABELS = ["Pre-due nudge", "Due-date reminder", "Firm follow-up", "Final notice"];

export default function SettingsPage() {
    const { user, logout } = useAuth();
    const { status: gmailStatus } = useGmailConnection();
    const [settings, setSettings] = useState(null);
    const [saving, setSaving] = useState(false);
    const [err, setErr] = useState("");
    const [suppressed, setSuppressed] = useState([]);
    const [timezones, setTimezones] = useState([]);

    // Delete-account dialog state
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [confirmEmail, setConfirmEmail] = useState("");
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        let alive = true;
        async function load() {
            try {
                const [s, sup, tz] = await Promise.all([
                    api.get("/settings"),
                    api.get("/suppressed-senders"),
                    api.get("/settings/timezones"),
                ]);
                if (!alive) return;
                setSettings(s.data);
                setSuppressed(sup.data.senders || []);
                setTimezones(tz.data.timezones || []);
            } catch (e) {
                if (alive) setErr(extractError(e));
            }
        }
        load();
        return () => { alive = false; };
    }, []);

    async function persist(patch, successMsg = "Saved") {
        setSaving(true);
        try {
            const { data } = await api.patch("/settings", patch);
            setSettings(data);
            toast.success(successMsg);
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setSaving(false);
        }
    }

    async function unsuppress(email) {
        try {
            await api.delete(`/suppressed-senders/${encodeURIComponent(email)}`);
            setSuppressed((prev) => prev.filter((s) => s.email !== email));
            toast.success("Removed from suppression list");
        } catch (e) {
            toast.error(extractError(e));
        }
    }

    async function doDelete() {
        setDeleting(true);
        try {
            await api.delete("/account", { data: { confirm_email: confirmEmail } });
            toast.success("Account deleted");
            await logout();
        } catch (e) {
            toast.error(extractError(e));
            setDeleting(false);
        }
    }

    if (err && !settings) {
        return (
            <div className="min-h-screen bg-background text-foreground">
                <TopNav />
                <main className="max-w-3xl mx-auto p-8">
                    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                        {err}
                    </div>
                </main>
            </div>
        );
    }

    if (!settings) {
        return (
            <div className="min-h-screen bg-background text-foreground">
                <TopNav />
                <main className="max-w-3xl mx-auto p-8 text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 mr-2 animate-spin inline" /> Loading settings…
                </main>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="settings-page">
            <TopNav />
            <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-14 space-y-10">
                <div>
                    <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">
                        Workspace
                    </div>
                    <h1 className="font-heading font-black text-3xl md:text-4xl tracking-tight">
                        Settings
                    </h1>
                    <p className="mt-2 text-sm text-muted-foreground">
                        Fine-tune when Scotive drafts each chase step. Due dates come from your invoices only.
                    </p>
                </div>

                <GmailAccountSection status={gmailStatus} />

                <ChasingTimingSection
                    settings={settings}
                    saving={saving}
                    onSave={persist}
                />

                <LateFeeSection settings={settings} saving={saving} onSave={persist} />

                <ScanWindowSection settings={settings} />

                <DailyDigestSection
                    settings={settings}
                    saving={saving}
                    onSave={persist}
                    timezones={timezones}
                />

                <SuppressedSendersSection
                    senders={suppressed}
                    onRemove={unsuppress}
                />

                <DangerZone
                    email={user?.email}
                    onDeleteClick={() => {
                        setConfirmEmail("");
                        setConfirmDelete(true);
                    }}
                />
            </main>

            <AlertDialog open={confirmDelete} onOpenChange={(o) => !deleting && setConfirmDelete(o)}>
                <AlertDialogContent data-testid="delete-account-dialog">
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete your Scotive account?</AlertDialogTitle>
                        <AlertDialogDescription>
                            This permanently removes your account, ledger, receipts, chase history,
                            Gmail connection and all extracted evidence. It cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="space-y-2">
                        <Label htmlFor="confirm-email" className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
                            Type your email to confirm
                        </Label>
                        <Input
                            id="confirm-email"
                            data-testid="delete-confirm-email"
                            value={confirmEmail}
                            onChange={(e) => setConfirmEmail(e.target.value)}
                            placeholder={user?.email}
                            autoFocus
                        />
                    </div>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleting} data-testid="delete-cancel">
                            Cancel
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={(e) => {
                                e.preventDefault();
                                doDelete();
                            }}
                            disabled={deleting || confirmEmail.trim().toLowerCase() !== (user?.email || "").toLowerCase()}
                            className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                            data-testid="delete-confirm-action">
                            {deleting ? "Deleting…" : "Delete forever"}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Gmail account
// ---------------------------------------------------------------------------
function GmailAccountSection({ status }) {
    return (
        <section data-testid="settings-gmail-account">
            <h2 className="font-heading font-bold text-xl">Gmail account</h2>
            <p className="mt-1 text-sm text-muted-foreground">
                Connect read + send access so Scotive can scan sent invoices and draft chasers from your inbox.
            </p>
            <Separator className="my-4" />
            <ConnectionPanel status={status} />
        </section>
    );
}

// ---------------------------------------------------------------------------
// Chasing timing
// ---------------------------------------------------------------------------
function ChasingTimingSection({ settings, saving, onSave }) {
    const [offsets, setOffsets] = useState(settings.escalation_offsets);
    const [followUpDays, setFollowUpDays] = useState(settings.follow_up_interval_days ?? 3);
    useEffect(() => { setOffsets(settings.escalation_offsets); }, [settings.escalation_offsets]);
    useEffect(() => { setFollowUpDays(settings.follow_up_interval_days ?? 3); }, [settings.follow_up_interval_days]);

    const dirty =
        JSON.stringify(offsets) !== JSON.stringify(settings.escalation_offsets)
        || followUpDays !== (settings.follow_up_interval_days ?? 3);

    function updateOffset(i, value) {
        const v = parseInt(value, 10);
        const next = [...offsets];
        next[i] = Number.isFinite(v) ? v : 0;
        setOffsets(next);
    }

    return (
        <Section
            title="Chasing timing"
            subtitle="When to draft each chase step relative to the due date. Past-due flips happen automatically on the next hourly sync — no grace buffer.">
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground mb-4 max-w-lg">
                Invoices move to <strong>Past due</strong> the day after their due date during the hourly sync (or Sync now).
            </div>
            <div className="mt-2 space-y-3">
                <Label>Escalation ladder</Label>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {ESCALATION_LABELS.map((label, i) => (
                        <div key={label} className="space-y-1.5">
                            <div className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                                {label}
                            </div>
                            <div className="flex items-baseline gap-1.5">
                                <Input
                                    type="number"
                                    min={-30}
                                    max={90}
                                    value={offsets[i] ?? 0}
                                    onChange={(e) => updateOffset(i, e.target.value)}
                                    className="max-w-[90px]"
                                    data-testid={`input-escalation-${i}`}
                                />
                                <span className="text-xs text-muted-foreground">
                                    {(offsets[i] ?? 0) < 0 ? "days before due" : (offsets[i] ?? 0) === 0 ? "on due date" : "days after due"}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
                <p className="text-[11px] text-muted-foreground">
                    Negative values chase before due; positives chase after. Nothing is ever auto-sent — Scotive drafts on these days for your review.
                </p>
            </div>

            <div className="mt-6 space-y-2 max-w-lg">
                <Label htmlFor="follow-up-interval">Follow-up interval (after you send)</Label>
                <div className="flex items-baseline gap-2">
                    <Input
                        id="follow-up-interval"
                        type="number"
                        min={1}
                        max={30}
                        value={followUpDays}
                        onChange={(e) => setFollowUpDays(parseInt(e.target.value, 10) || 1)}
                        className="max-w-[90px]"
                        data-testid="input-follow-up-interval"
                    />
                    <span className="text-xs text-muted-foreground">days with no client reply before the next escalation draft</span>
                </div>
                <p className="text-[11px] text-muted-foreground">
                    Applies after you send a follow-up. Scotive drafts the next step for your review — never auto-sends.
                </p>
            </div>

            <SectionFooter
                dirty={dirty}
                saving={saving}
                onSave={() => onSave({
                    escalation_offsets: offsets,
                    follow_up_interval_days: followUpDays,
                }, "Chasing timing saved")}
                testid="save-chasing-timing"
            />
        </Section>
    );
}

// ---------------------------------------------------------------------------
// Late fees
// ---------------------------------------------------------------------------
function LateFeeSection({ settings, saving, onSave }) {
    const [enabled, setEnabled] = useState(settings.late_fee_enabled);
    const [text, setText] = useState(settings.late_fee_text || "");
    useEffect(() => { setEnabled(settings.late_fee_enabled); }, [settings.late_fee_enabled]);
    useEffect(() => { setText(settings.late_fee_text || ""); }, [settings.late_fee_text]);

    const dirty = enabled !== settings.late_fee_enabled || text !== (settings.late_fee_text || "");

    return (
        <Section
            title="Late fees"
            subtitle="When enabled, the final notice draft can reference your late-fee wording.">
            <div className="flex items-center justify-between gap-4">
                <div>
                    <div className="font-medium">Mention a late fee in the final notice</div>
                    <div className="text-xs text-muted-foreground">Only applies to the final step of the escalation ladder.</div>
                </div>
                <Switch
                    checked={enabled}
                    onCheckedChange={setEnabled}
                    data-testid="toggle-late-fee"
                />
            </div>
            {enabled ? (
                <div className="mt-4 space-y-2">
                    <Label htmlFor="late-fee-text">Late-fee wording</Label>
                    <Textarea
                        id="late-fee-text"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        placeholder="e.g. A 1.5% monthly late fee applies to balances over 30 days past due."
                        maxLength={280}
                        rows={2}
                        data-testid="input-late-fee-text"
                    />
                    <div className="text-[11px] font-mono text-muted-foreground">{text.length} / 280</div>
                </div>
            ) : null}

            <SectionFooter
                dirty={dirty}
                saving={saving}
                onSave={() => onSave({ late_fee_enabled: enabled, late_fee_text: text }, "Late fee settings saved")}
                testid="save-late-fee"
            />
        </Section>
    );
}

// ---------------------------------------------------------------------------
// Gmail sync (read-only info)
// ---------------------------------------------------------------------------
function ScanWindowSection({ settings }) {
    const seedDays = settings.seed_lookback_days ?? 90;
    const syncLookback = settings.sync_lookback ?? "1h";

    return (
        <Section
            title="Gmail sync"
            subtitle="One job handles onboarding, hourly background sync, and Sync now.">
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground max-w-lg space-y-1">
                <p>
                    <strong>First setup:</strong> last <strong>{seedDays} days</strong> of sent mail → you pick what to track.
                </p>
                <p>
                    <strong>After that:</strong> sync runs every hour and checks the last <strong>{syncLookback}</strong> of sent mail (same as Sync now).
                </p>
                <p>
                    <strong>Due dates:</strong> taken only from the invoice email or PDF. If none is found, you add it manually — Scotive never guesses.
                </p>
            </div>
        </Section>
    );
}

// ---------------------------------------------------------------------------
// Daily digest
// ---------------------------------------------------------------------------
function DailyDigestSection({ settings, saving, onSave, timezones }) {
    const initialHour = settings.daily_digest_hour ?? settings.daily_digest_hour_utc ?? 9;
    const initialTz = settings.daily_digest_timezone || "UTC";
    const [enabled, setEnabled] = useState(!!settings.daily_digest_enabled);
    const [hour, setHour] = useState(initialHour);
    const [tz, setTz] = useState(initialTz);
    const [sending, setSending] = useState(false);
    useEffect(() => { setEnabled(!!settings.daily_digest_enabled); }, [settings.daily_digest_enabled]);
    useEffect(() => { setHour(settings.daily_digest_hour ?? settings.daily_digest_hour_utc ?? 9); },
        [settings.daily_digest_hour, settings.daily_digest_hour_utc]);
    useEffect(() => { setTz(settings.daily_digest_timezone || "UTC"); }, [settings.daily_digest_timezone]);
    const dirty =
        enabled !== !!settings.daily_digest_enabled ||
        hour !== initialHour ||
        tz !== initialTz;

    // Compute "next digest at" in the user's chosen timezone for reassurance.
    let nextAtLabel = "";
    try {
        const now = new Date();
        // Round display "now" to the top of the current hour in the target tz so
        // "next send at Xam" doesn't include stray minutes.
        const parts = new Intl.DateTimeFormat("en-US", {
            timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
        }).formatToParts(now);
        const currentHourInTz = parseInt(parts.find((p) => p.type === "hour")?.value || "0", 10);
        const currentMinInTz = parseInt(parts.find((p) => p.type === "minute")?.value || "0", 10);
        // If we're already past the target hour today, schedule for tomorrow.
        let hoursUntil = hour - currentHourInTz;
        if (hoursUntil < 0 || (hoursUntil === 0 && currentMinInTz > 0)) hoursUntil += 24;
        const nextMs = now.getTime() + hoursUntil * 3600 * 1000 - currentMinInTz * 60 * 1000;
        const next = new Date(nextMs);
        const fmt = new Intl.DateTimeFormat("en-US", {
            timeZone: tz,
            weekday: "short",
            hour: "numeric",
            hour12: true,
        });
        nextAtLabel = `Next send: ${fmt.format(next)} (${tz.replace("_", " ")})`;
    } catch {
        nextAtLabel = "";
    }

    async function sendNow() {
        setSending(true);
        try {
            const { data } = await api.post("/digest/send-now");
            if (data.status === "sent") {
                toast.success("Digest sent to your inbox");
            } else if (data.reason === "empty") {
                toast.info("Nothing to send today — you're all caught up.");
            } else if (data.reason === "no_gmail" || data.reason === "no_send_scope") {
                toast.error("Connect Gmail with send scope to email digests.");
            } else if (String(data.reason || "").startsWith("auth_error")) {
                toast.error("Gmail auth expired — reconnect in Gmail account below.");
            } else {
                toast.error(`Digest not sent: ${data.reason || "unknown"}`);
            }
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setSending(false);
        }
    }

    return (
        <Section
            title="Daily digest email"
            subtitle="Once a day, Scotive can email you a summary of what needs action — past due, broken promises, and resolved payments. Sent from your own connected Gmail. Silent when there's nothing to report.">
            <div className="flex items-center justify-between gap-4">
                <div>
                    <div className="font-medium">Send me a daily digest</div>
                    <div className="text-xs text-muted-foreground">
                        Last sent: {settings.last_digest_sent_at ? new Date(settings.last_digest_sent_at).toLocaleString() : "never"}
                    </div>
                </div>
                <Switch checked={enabled} onCheckedChange={setEnabled} data-testid="toggle-daily-digest" />
            </div>
            {enabled ? (
                <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div className="space-y-2">
                        <Label htmlFor="digest-hour">Send hour</Label>
                        <Select value={String(hour)} onValueChange={(v) => setHour(parseInt(v, 10))}>
                            <SelectTrigger data-testid="select-digest-hour">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {Array.from({ length: 24 }, (_, i) => i).map((h) => {
                                    const suffix = h === 0 ? "12:00 AM" : h < 12 ? `${h}:00 AM` : h === 12 ? "12:00 PM" : `${h - 12}:00 PM`;
                                    return (
                                        <SelectItem key={h} value={String(h)} data-testid={`digest-hour-${h}`}>
                                            {suffix} ({String(h).padStart(2, "0")}:00)
                                        </SelectItem>
                                    );
                                })}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="digest-tz">Timezone</Label>
                        <Select value={tz} onValueChange={setTz}>
                            <SelectTrigger data-testid="select-digest-tz">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="max-h-72">
                                {(timezones || []).map((z) => (
                                    <SelectItem key={z.value} value={z.value} data-testid={`digest-tz-${z.value}`}>
                                        {z.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="sm:col-span-2">
                        <p className="text-[11px] text-muted-foreground" data-testid="digest-next-send">
                            {nextAtLabel || "Local time zones honored — the digest arrives in your inbox at the chosen hour."}
                        </p>
                    </div>
                </div>
            ) : null}
            <SectionFooter
                dirty={dirty}
                saving={saving}
                onSave={() => onSave({
                    daily_digest_enabled: enabled,
                    daily_digest_hour: hour,
                    daily_digest_timezone: tz,
                }, "Digest settings saved")}
                testid="save-digest"
            />
            <div className="mt-5 pt-4 border-t border-border flex items-center justify-end gap-3">
                <span className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                    Preview
                </span>
                <Button variant="outline" size="sm" onClick={sendNow} disabled={sending} data-testid="digest-send-now">
                    {sending ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null}
                    Send digest to me now
                </Button>
            </div>
        </Section>
    );
}

// ---------------------------------------------------------------------------
// Suppressed senders
// ---------------------------------------------------------------------------
function SuppressedSendersSection({ senders, onRemove }) {
    return (
        <Section
            title="Suppressed senders"
            subtitle="Emails from these addresses are ignored by the AI pipeline. Add senders from the Review queue's Not payment-related action.">
            {senders.length === 0 ? (
                <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground" data-testid="suppressed-empty">
                    Nothing suppressed yet.
                </div>
            ) : (
                <ul className="rounded-2xl border border-border bg-card divide-y divide-border" data-testid="suppressed-list">
                    {senders.map((s) => (
                        <li key={s.email} className="px-4 py-3 flex items-center justify-between gap-3">
                            <div className="min-w-0">
                                <div className="font-mono text-sm truncate">{s.email}</div>
                                {s.created_at ? (
                                    <div className="text-[11px] text-muted-foreground">
                                        Suppressed {new Date(s.created_at).toLocaleDateString()}
                                    </div>
                                ) : null}
                            </div>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => onRemove(s.email)}
                                data-testid="unsuppress-btn">
                                Remove
                            </Button>
                        </li>
                    ))}
                </ul>
            )}
        </Section>
    );
}

// ---------------------------------------------------------------------------
// Danger zone
// ---------------------------------------------------------------------------
function DangerZone({ email, onDeleteClick }) {
    return (
        <section data-testid="danger-zone">
            <h2 className="font-heading font-bold text-xl mb-3 text-red-800">Danger zone</h2>
            <div className="rounded-2xl border border-red-200 bg-red-50/40 p-6">
                <div className="flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-700 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                        <div className="font-medium text-red-900">Delete this account</div>
                        <p className="mt-1 text-sm text-red-800/90">
                            Permanently removes <span className="font-mono">{email}</span>, the
                            ledger, all receipts, chase history, Gmail connection and extracted
                            evidence. There is no undo.
                        </p>
                    </div>
                    <Button
                        variant="destructive"
                        onClick={onDeleteClick}
                        data-testid="delete-account-btn">
                        <Trash2 className="w-4 h-4 mr-1.5" /> Delete account
                    </Button>
                </div>
            </div>
        </section>
    );
}

// ---------------------------------------------------------------------------
// Section shell
// ---------------------------------------------------------------------------
function Section({ title, subtitle, children }) {
    return (
        <section>
            <h2 className="font-heading font-bold text-xl">{title}</h2>
            {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
            <Separator className="my-4" />
            <div className="rounded-2xl border border-border bg-card p-6">{children}</div>
        </section>
    );
}

function SectionFooter({ dirty, saving, onSave, testid }) {
    if (!dirty) return null;
    return (
        <div className="mt-5 pt-4 border-t border-border flex items-center justify-end gap-3">
            <span className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                Unsaved changes
            </span>
            <Button onClick={onSave} disabled={saving} data-testid={testid}>
                {saving ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
                Save
            </Button>
        </div>
    );
}
