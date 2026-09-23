"use client";
import { useMemo, useState } from "react";
import { CalendarClock, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { shortWaitDate } from "@/lib/chase";
import { cn } from "@/lib/utils";

function toIsoDate(value) {
    if (!value) return null;
    if (typeof value === "string") return value.slice(0, 10);
    const y = value.getFullYear();
    const m = String(value.getMonth() + 1).padStart(2, "0");
    const d = String(value.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function parseIsoDay(value) {
    const iso = toIsoDate(value);
    if (!iso) return null;
    const parsed = new Date(`${iso}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function startOfDay(value) {
    const d = value instanceof Date ? new Date(value) : parseIsoDay(value);
    if (!d) return null;
    d.setHours(0, 0, 0, 0);
    return d;
}

function todayDate() {
    return startOfDay(new Date());
}

export async function waitUntilInvoice(invoiceId, date, { onChanged, successMessage } = {}) {
    await api.post(`/v1/invoices/${invoiceId}/action`, { action: "wait_until", wait_until: date });
    toast.success(successMessage || `Sleeping until ${shortWaitDate(date)}`);
    await onChanged?.();
}

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function DayCalendar({ selected, minDate, onPick }) {
    const selectedDay = startOfDay(selected);
    const minDay = startOfDay(minDate) || todayDate();
    const [cursor, setCursor] = useState(() => {
        const seed = selectedDay || todayDate();
        return new Date(seed.getFullYear(), seed.getMonth(), 1);
    });

    const cells = useMemo(() => {
        const year = cursor.getFullYear();
        const month = cursor.getMonth();
        const lead = new Date(year, month, 1).getDay();
        const last = new Date(year, month + 1, 0).getDate();
        const days = [];
        for (let i = 0; i < lead; i += 1) days.push(null);
        for (let d = 1; d <= last; d += 1) days.push(new Date(year, month, d));
        return days;
    }, [cursor]);

    const today = todayDate();

    return (
        <div className="w-[252px] p-3" data-testid="wait-until-calendar">
            <div className="mb-2 flex items-center justify-between">
                <button
                    type="button"
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
                    aria-label="Previous month"
                >
                    <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="text-sm font-medium">
                    {cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
                </div>
                <button
                    type="button"
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
                    aria-label="Next month"
                >
                    <ChevronRight className="h-4 w-4" />
                </button>
            </div>
            <div className="grid grid-cols-7 text-center text-[11px] text-muted-foreground">
                {WEEKDAYS.map((day) => (
                    <div key={day} className="py-1">{day}</div>
                ))}
            </div>
            <div className="grid grid-cols-7">
                {cells.map((day, index) => {
                    if (!day) return <div key={`empty-${index}`} className="h-8" />;
                    const iso = toIsoDate(day);
                    const disabled = day < minDay;
                    const isSelected = selectedDay && toIsoDate(day) === toIsoDate(selectedDay);
                    const isToday = toIsoDate(day) === toIsoDate(today);
                    return (
                        <button
                            key={iso}
                            type="button"
                            disabled={disabled}
                            onClick={() => onPick(iso)}
                            className={cn(
                                "h-8 w-8 justify-self-center rounded-md text-sm",
                                disabled && "cursor-not-allowed text-muted-foreground/40",
                                !disabled && !isSelected && "hover:bg-muted",
                                isToday && !isSelected && "font-semibold text-foreground",
                                isSelected && "bg-primary text-primary-foreground hover:bg-primary"
                            )}
                        >
                            {day.getDate()}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

export function SnoozeControl({
    invoice,
    label = "Snooze",
    presetDate = null,
    defaultDate = null,
    onChanged,
    size = "sm",
    className = "",
    successMessage = null,
    testId = "snooze-open",
}) {
    const saved = toIsoDate(defaultDate || invoice?.expected_pay_date) || "";
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);

    async function pickDay(iso) {
        if (!iso || !invoice?._id || busy) return;
        setBusy(true);
        try {
            await waitUntilInvoice(invoice._id, iso, {
                onChanged,
                successMessage: typeof successMessage === "function" ? successMessage(iso) : successMessage,
            });
            setOpen(false);
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    if (presetDate) {
        return (
            <Button
                size={size}
                variant="outline"
                disabled={busy}
                className={className}
                onClick={() => pickDay(presetDate)}
                data-testid={testId}
            >
                {label}
            </Button>
        );
    }

    return (
        <div className={`inline-flex ${className}`} onClick={(e) => e.stopPropagation()}>
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        type="button"
                        size={size}
                        variant="outline"
                        disabled={busy}
                        data-testid={testId}
                    >
                        <CalendarClock className="w-3.5 h-3.5 mr-1.5" />
                        {label}
                    </Button>
                </PopoverTrigger>
                <PopoverContent
                    align="end"
                    className="w-auto p-0"
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => e.stopPropagation()}
                >
                    <DayCalendar selected={saved} minDate={todayDate()} onPick={pickDay} />
                </PopoverContent>
            </Popover>
        </div>
    );
}

export function CheckBackSelect({ value, onChange }) {
    const [open, setOpen] = useState(false);
    const selected = toIsoDate(value) || "";

    return (
        <div className="flex flex-wrap items-center gap-2" data-testid="check-back-select">
            <span className="text-sm text-muted-foreground">If still unpaid, check back in:</span>
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button type="button" variant="outline" size="sm" className="h-8 font-normal">
                        <CalendarClock className="mr-1.5 h-3.5 w-3.5" />
                        {selected ? shortWaitDate(selected) : "Pick a date"}
                    </Button>
                </PopoverTrigger>
                <PopoverContent align="start" side="top" className="w-auto p-0">
                    <DayCalendar
                        selected={selected}
                        minDate={todayDate()}
                        onPick={(iso) => {
                            onChange(iso);
                            setOpen(false);
                        }}
                    />
                </PopoverContent>
            </Popover>
        </div>
    );
}

export function FollowUpDateField({ value, onChange, id = "follow-up-date", compact = false }) {
    const [open, setOpen] = useState(false);
    const selected = toIsoDate(value) || "";

    return (
        <div className={compact ? "inline-flex items-center gap-2" : "space-y-1.5"}>
            {compact ? (
                <span className="text-xs text-muted-foreground">If unpaid</span>
            ) : (
                <label className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground" htmlFor={id}>
                    Follow up if unpaid on
                </label>
            )}
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        id={id}
                        type="button"
                        variant="outline"
                        size={compact ? "sm" : "default"}
                        className={compact ? "h-8 justify-start font-normal" : "h-9 w-[170px] justify-start font-normal"}
                        data-testid="wait-until-date"
                    >
                        <CalendarClock className="mr-2 h-3.5 w-3.5" />
                        {selected ? shortWaitDate(selected) : "Pick a date"}
                    </Button>
                </PopoverTrigger>
                <PopoverContent align="start" className="w-auto p-0">
                    <DayCalendar
                        selected={selected}
                        minDate={todayDate()}
                        onPick={(iso) => {
                            onChange(iso);
                            setOpen(false);
                        }}
                    />
                </PopoverContent>
            </Popover>
        </div>
    );
}

export function WaitUntilControl({ invoice, onChanged, compact = false, className = "" }) {
    return (
        <SnoozeControl
            invoice={invoice}
            label={compact ? "Snooze" : "Snooze until date"}
            defaultDate={invoice?.suggested_wait_date || invoice?.expected_pay_date}
            onChanged={onChanged}
            size={compact ? "sm" : "default"}
            className={className}
        />
    );
}
