"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Loader2, Save, Trash2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
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
import { api, extractError, unwrapData } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ConnectionPanel } from "@/components/ConnectionPanel";
import { SettingsSkeleton } from "@/components/PageSkeletons";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { useQboConnection } from "@/hooks/useQboConnection";
import { QboConnectionPanel } from "@/components/QboConnectionPanel";

const DEFAULT_REMINDERS = {
    before_due: { enabled: true, days: 3 },
    on_due: { enabled: true },
    overdue: { enabled: true, days: 7 },
};

const DEFAULT_SETTINGS = {
    friendly_reminders: DEFAULT_REMINDERS,
    friendly_auto_send: true,
};

function clampDay(value, fallback, min, max) {
    const n = parseInt(value, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.min(max, Math.max(min, n));
}

function remindersFromSettings(settings) {
    const raw = settings?.friendly_reminders;
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        return {
            before_due: {
                enabled: raw.before_due?.enabled !== false,
                days: clampDay(raw.before_due?.days, 3, 1, 30),
            },
            on_due: { enabled: raw.on_due?.enabled !== false },
            overdue: {
                enabled: raw.overdue?.enabled !== false,
                days: clampDay(raw.overdue?.days, 7, 1, 90),
            },
        };
    }
    const offsets = Array.isArray(settings?.escalation_offsets) ? settings.escalation_offsets : [-3, 0, 7];
    return {
        before_due: { enabled: offsets[0] != null, days: clampDay(Math.abs(offsets[0]), 3, 1, 30) },
        on_due: { enabled: offsets[1] != null },
        overdue: { enabled: offsets[2] != null, days: clampDay(Math.abs(offsets[2]), 7, 1, 90) },
    };
}

export default function SettingsPage() {
    const { user, logout } = useAuth();
    const { status: gmailStatus } = useGmailConnection();
    const { status: qboStatus } = useQboConnection();
    const [settings, setSettings] = useState(null);
    const [settingsReady, setSettingsReady] = useState(false);
    const [saving, setSaving] = useState(false);
    const [timezones, setTimezones] = useState([]);

    // Delete-account dialog state
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [confirmEmail, setConfirmEmail] = useState("");
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        let alive = true;
        async function load() {
            const [settingsRes, tzRes] = await Promise.allSettled([
                api.get("/v1/settings"),
                api.get("/v1/settings/timezones"),
            ]);
            if (!alive) return;
            if (settingsRes.status === "fulfilled") {
                setSettings(unwrapData(settingsRes.value.data) || DEFAULT_SETTINGS);
            } else {
                setSettings(DEFAULT_SETTINGS);
            }
            if (tzRes.status === "fulfilled") {
                setTimezones(unwrapData(tzRes.value.data)?.timezones || []);
            }
            setSettingsReady(true);
        }
        load();
        return () => { alive = false; };
    }, []);

    async function persist(patch, successMsg = "Saved") {
        setSaving(true);
        try {
            const { data } = await api.patch("/v1/settings", patch);
            setSettings(unwrapData(data) || data);
            toast.success(successMsg);
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setSaving(false);
        }
    }

    async function doDelete() {
        setDeleting(true);
        try {
            await api.delete("/v1/auth/account", { data: { confirm_email: confirmEmail } });
            toast.success("Account deleted");
            await logout();
        } catch (e) {
            toast.error(extractError(e));
            setDeleting(false);
        }
    }

    if (!settingsReady || !settings) {
        return (
            <AppShell width="3xl" mainClassName="py-10 md:py-14">
                <SettingsSkeleton />
            </AppShell>
        );
    }

    return (
        <AppShell
            testId="settings-page"
            width="3xl"
            mainClassName="py-10 md:py-14 space-y-10"
            afterMain={(
                <AlertDialog open={confirmDelete} onOpenChange={(o) => !deleting && setConfirmDelete(o)}>
                    <AlertDialogContent data-testid="delete-account-dialog">
                        <AlertDialogHeader>
                            <AlertDialogTitle>Delete your Scotive account?</AlertDialogTitle>
                            <AlertDialogDescription>
                                This permanently removes your account, ledger, receipts, chase history,
                                Gmail and QuickBooks connections, and all extracted evidence. It cannot be undone.
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <div className="space-y-2">
                            <Label htmlFor="confirm-email">
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
            )}
        >
                <div>
                    <div className="eyebrow mb-2">
                        Workspace
                    </div>
                    <h1 className="type-display text-3xl md:text-4xl">
                        Settings
                    </h1>
                    <p className="type-body mt-2 text-sm">
                        Mailbox, QuickBooks, and when Friendly reminders send.
                    </p>
                </div>

                <GmailAccountSection status={gmailStatus} />

                <QboAccountSection status={qboStatus} />

                <ChasingTimingSection
                    settings={settings}
                    saving={saving}
                    onSave={persist}
                />

                {/* Late fees hidden for MVP — flip to true to restore. */}
                {false ? (
                    <LateFeeSection settings={settings} saving={saving} onSave={persist} />
                ) : null}

                {/* Gmail sync info panel removed from Settings — not user-configurable. */}

                <DailyDigestSection
                    settings={settings}
                    saving={saving}
                    onSave={persist}
                    timezones={timezones}
                />

                <DangerZone
                    email={user?.email}
                    onDeleteClick={() => {
                        setConfirmEmail("");
                        setConfirmDelete(true);
                    }}
                />
        </AppShell>
    );
}

// ---------------------------------------------------------------------------
// Gmail account
// ---------------------------------------------------------------------------
function GmailAccountSection({ status }) {
    return (
        <section data-testid="settings-gmail-account">
            <h2 className="type-title text-xl">Email mailbox</h2>
            <p className="mt-1 text-sm text-muted-foreground">
                Connect Gmail or Outlook so Scotive can match invoice conversations and send follow-ups from your address.
            </p>
            <Separator className="my-4" />
            <ConnectionPanel status={status} />
        </section>
    );
}

function QboAccountSection({ status }) {
    return (
        <section data-testid="settings-qbo-account">
            <h2 className="type-title text-xl">QuickBooks Online</h2>
            <p className="mt-1 text-sm text-muted-foreground">
                Required — invoices are imported from QuickBooks. Status and chasing stay in Scotive; your mailbox matches client replies.
            </p>
            <Separator className="my-4" />
            <QboConnectionPanel status={status} />
        </section>
    );
}

// ---------------------------------------------------------------------------
// Chasing timing
// ---------------------------------------------------------------------------
function DayField({ id, value, onChange, disabled, min, max, testid }) {
    return (
        <Input
            id={id}
            type="text"
            inputMode="numeric"
            disabled={disabled}
            value={value}
            onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, "").slice(0, 2))}
            onBlur={() => {
                const next = clampDay(value, min, min, max);
                onChange(String(next));
            }}
            className="h-8 w-14 px-1 text-center"
            data-testid={testid}
        />
    );
}

function ChasingTimingSection({ settings, saving, onSave }) {
    const saved = remindersFromSettings(settings);
    const [beforeOn, setBeforeOn] = useState(saved.before_due.enabled);
    const [beforeDays, setBeforeDays] = useState(String(saved.before_due.days));
    const [onDue, setOnDue] = useState(saved.on_due.enabled);
    const [overdueOn, setOverdueOn] = useState(saved.overdue.enabled);
    const [overdueDays, setOverdueDays] = useState(String(saved.overdue.days));
    const [autoSend, setAutoSend] = useState(settings.friendly_auto_send !== false);

    useEffect(() => {
        const next = remindersFromSettings(settings);
        setBeforeOn(next.before_due.enabled);
        setBeforeDays(String(next.before_due.days));
        setOnDue(next.on_due.enabled);
        setOverdueOn(next.overdue.enabled);
        setOverdueDays(String(next.overdue.days));
    }, [settings.friendly_reminders, settings.escalation_offsets]);
    useEffect(() => { setAutoSend(settings.friendly_auto_send !== false); }, [settings.friendly_auto_send]);

    const draft = {
        before_due: { enabled: beforeOn, days: clampDay(beforeDays, saved.before_due.days, 1, 30) },
        on_due: { enabled: onDue },
        overdue: { enabled: overdueOn, days: clampDay(overdueDays, saved.overdue.days, 1, 90) },
    };
    const dirty =
        JSON.stringify(draft) !== JSON.stringify(saved)
        || autoSend !== (settings.friendly_auto_send !== false);

    return (
        <Section
            title="Friendly cadence"
            subtitle="Turn each reminder on or off. After the last one you leave on, the invoice moves to Needs you — you write and send. Cadence pauses if they reply or pay.">
            <div className="flex items-center justify-between gap-4 max-w-lg mb-4">
                <div>
                    <div className="font-medium">Send Friendly reminders automatically</div>
                    <div className="text-xs text-muted-foreground">
                        Off = draft only, you still click send. Nothing firmer is auto-sent.
                    </div>
                </div>
                <Switch
                    checked={autoSend}
                    onCheckedChange={setAutoSend}
                    data-testid="toggle-friendly-auto-send"
                />
            </div>
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground mb-4 max-w-lg">
                Invoices move to <strong>Past due</strong> the day after their due date during the hourly sync (or Sync now).
            </div>
            <div className="mt-2 max-w-lg space-y-3">
                <Label>Reminders</Label>
                <div className="space-y-3">
                    <label className="flex items-start gap-3 text-sm">
                        <input
                            type="checkbox"
                            className="mt-1 h-4 w-4 shrink-0 rounded border border-primary accent-primary"
                            checked={beforeOn}
                            onChange={(e) => setBeforeOn(e.target.checked)}
                            data-testid="toggle-reminder-before-due"
                        />
                        <span className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 ${beforeOn ? "text-foreground" : "text-muted-foreground"}`}>
                            <span className="font-medium">Before due:</span>
                            <span>Send</span>
                            <DayField
                                id="before-due-days"
                                value={beforeDays}
                                onChange={setBeforeDays}
                                disabled={!beforeOn}
                                min={1}
                                max={30}
                                testid="input-reminder-before-due"
                            />
                            <span>days before due date</span>
                        </span>
                    </label>
                    <label className="flex items-start gap-3 text-sm">
                        <input
                            type="checkbox"
                            className="mt-1 h-4 w-4 shrink-0 rounded border border-primary accent-primary"
                            checked={onDue}
                            onChange={(e) => setOnDue(e.target.checked)}
                            data-testid="toggle-reminder-on-due"
                        />
                        <span className={onDue ? "text-foreground" : "text-muted-foreground"}>
                            <span className="font-medium">On due date:</span> Send on due date
                        </span>
                    </label>
                    <label className="flex items-start gap-3 text-sm">
                        <input
                            type="checkbox"
                            className="mt-1 h-4 w-4 shrink-0 rounded border border-primary accent-primary"
                            checked={overdueOn}
                            onChange={(e) => setOverdueOn(e.target.checked)}
                            data-testid="toggle-reminder-overdue"
                        />
                        <span className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 ${overdueOn ? "text-foreground" : "text-muted-foreground"}`}>
                            <span className="font-medium">Overdue follow-up:</span>
                            <span>Send</span>
                            <DayField
                                id="overdue-days"
                                value={overdueDays}
                                onChange={setOverdueDays}
                                disabled={!overdueOn}
                                min={1}
                                max={90}
                                testid="input-reminder-overdue"
                            />
                            <span>days after due date</span>
                        </span>
                    </label>
                </div>
                <p className="text-[11px] text-muted-foreground">
                    Uncheck a row to skip that reminder. After the last one still on, you take over from Needs you.
                </p>
            </div>

            <SectionFooter
                dirty={dirty}
                saving={saving}
                onSave={() => onSave({
                    friendly_reminders: draft,
                    friendly_auto_send: autoSend,
                }, "Cadence saved")}
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

    return (
        <Section
            title="Mailbox sync"
            subtitle="Sync now and the hourly job refresh QuickBooks invoices and match conversations.">
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground max-w-lg space-y-1">
                <p>
                    <strong>Invoices:</strong> imported from QuickBooks. New and paid invoices sync on the hour (and when you hit Sync now).
                </p>
                <p>
                    <strong>Conversations:</strong> Scotive matches each open invoice to the Gmail or Outlook thread, then watches replies.
                </p>
                <p>
                    <strong>Due dates:</strong> taken from QuickBooks. If none is set, you add it manually — Scotive never guesses.
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
    const initialTz = settings.daily_digest_timezone || settings.time_zone || "UTC";
    const [enabled, setEnabled] = useState(!!settings.daily_digest_enabled);
    const [hour, setHour] = useState(initialHour);
    const [tz, setTz] = useState(initialTz);
    useEffect(() => { setEnabled(!!settings.daily_digest_enabled); }, [settings.daily_digest_enabled]);
    useEffect(() => { setHour(settings.daily_digest_hour ?? settings.daily_digest_hour_utc ?? 9); },
        [settings.daily_digest_hour, settings.daily_digest_hour_utc]);
    useEffect(() => { setTz(settings.daily_digest_timezone || settings.time_zone || "UTC"); },
        [settings.daily_digest_timezone, settings.time_zone]);
    const dirty =
        enabled !== !!settings.daily_digest_enabled ||
        hour !== initialHour ||
        tz !== initialTz;

    let nextAtLabel = "";
    try {
        const now = new Date();
        const parts = new Intl.DateTimeFormat("en-US", {
            timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
        }).formatToParts(now);
        const currentHourInTz = parseInt(parts.find((p) => p.type === "hour")?.value || "0", 10);
        const currentMinInTz = parseInt(parts.find((p) => p.type === "minute")?.value || "0", 10);
        let hoursUntil = 8 - currentHourInTz;
        if (hoursUntil < 0 || (hoursUntil === 0 && currentMinInTz > 0)) hoursUntil += 24;
        const nextMs = now.getTime() + hoursUntil * 3600 * 1000 - currentMinInTz * 60 * 1000;
        const next = new Date(nextMs);
        const fmt = new Intl.DateTimeFormat("en-US", {
            timeZone: tz,
            weekday: "short",
            hour: "numeric",
            hour12: true,
        });
        nextAtLabel = `Next Friendly morning: ${fmt.format(next)} (${tz.replace("_", " ")})`;
    } catch {
        nextAtLabel = "";
    }

    return (
        <Section
            title="Timezone"
            subtitle="Friendly cadence runs at 08:00 in this timezone and sends at 10:15. After that, you send from Needs you.">
            <div className="space-y-2 max-w-lg">
                <Label htmlFor="digest-tz">Workspace timezone</Label>
                <Select value={tz} onValueChange={setTz}>
                    <SelectTrigger data-testid="select-digest-tz">
                        <SelectValue placeholder="Select timezone" />
                    </SelectTrigger>
                    <SelectContent className="max-h-72">
                        {tz && !(timezones || []).some((z) => z.value === tz) ? (
                            <SelectItem value={tz} data-testid={`digest-tz-${tz}`}>
                                {tz.replace(/_/g, " ")}
                            </SelectItem>
                        ) : null}
                        {(timezones || []).map((z) => (
                            <SelectItem key={z.value} value={z.value} data-testid={`digest-tz-${z.value}`}>
                                {z.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground" data-testid="digest-next-send">
                    {nextAtLabel || "Cadence uses this timezone for the 08:00 morning pass."}
                </p>
            </div>

            <div className="flex items-center justify-between gap-4 mt-6 max-w-lg">
                <div>
                    <div className="font-medium">Email a daily digest</div>
                    <div className="text-xs text-muted-foreground">
                        Sends what needs you today — past due, broken promises, says paid, needs reply — at this hour.
                    </div>
                </div>
                <Switch checked={enabled} onCheckedChange={setEnabled} data-testid="toggle-daily-digest" />
            </div>
            {enabled ? (
                <div className="mt-5 max-w-lg space-y-2">
                    <Label htmlFor="digest-hour">Preferred hour</Label>
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
            ) : null}
            <SectionFooter
                dirty={dirty}
                saving={saving}
                onSave={() => onSave({
                    daily_digest_enabled: enabled,
                    daily_digest_hour: hour,
                    daily_digest_timezone: tz,
                }, "Timezone and digest saved")}
                testid="save-digest"
            />
        </Section>
    );
}

// ---------------------------------------------------------------------------
// Danger zone
// ---------------------------------------------------------------------------
function DangerZone({ email, onDeleteClick }) {
    return (
        <section data-testid="danger-zone">
            <h2 className="type-title text-xl mb-3 text-red-800">Danger zone</h2>
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
            <h2 className="type-title text-xl">{title}</h2>
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
            <span className="type-label text-muted-foreground">
                Unsaved changes
            </span>
            <Button onClick={onSave} disabled={saving} data-testid={testid}>
                {saving ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
                Save
            </Button>
        </div>
    );
}
