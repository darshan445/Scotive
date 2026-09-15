"use client";

import { useState } from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import {
    ANNUAL_EFFECTIVE_MONTHLY,
    ANNUAL_MONTHS_FREE,
    ANNUAL_TOTAL,
    MONTHLY_PRICE,
    PLAN_FEATURES,
    TRIAL_CTA,
    TRIAL_LABEL,
} from "@/lib/site";

export function PricingPlans() {
    const [yearly, setYearly] = useState(false);

    return (
        <div>
            <div
                className="flex justify-center mb-10"
                role="group"
                aria-label="Billing period"
            >
                <div className="inline-flex rounded-full border border-border bg-muted/40 p-1">
                    <button
                        type="button"
                        className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                            !yearly
                                ? "bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                        }`}
                        aria-pressed={!yearly}
                        onClick={() => setYearly(false)}
                    >
                        Monthly
                    </button>
                    <button
                        type="button"
                        className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                            yearly
                                ? "bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                        }`}
                        aria-pressed={yearly}
                        onClick={() => setYearly(true)}
                    >
                        Yearly
                        <span className="ml-1.5 text-[11px] font-semibold text-primary">
                            {ANNUAL_MONTHS_FREE} months free
                        </span>
                    </button>
                </div>
            </div>

            <article className="max-w-md mx-auto rounded-2xl border border-primary bg-card p-7 flex flex-col shadow-lg shadow-primary/10">
                <h2 className="type-title text-2xl">Scotive</h2>
                <p className="type-body mt-1 text-sm">
                    For agencies and consultants with a pile of open invoices.
                </p>
                {yearly ? (
                    <div className="mt-6">
                        <p className="flex items-baseline gap-1">
                            <span className="type-display text-5xl">${ANNUAL_EFFECTIVE_MONTHLY}</span>
                            <span className="text-muted-foreground text-sm">per month</span>
                        </p>
                        <p className="type-body mt-2 text-sm text-muted-foreground">
                            Billed ${ANNUAL_TOTAL}/year. Save {ANNUAL_MONTHS_FREE} months vs monthly.
                        </p>
                    </div>
                ) : (
                    <p className="mt-6 flex items-baseline gap-1">
                        <span className="type-display text-5xl">${MONTHLY_PRICE}</span>
                        <span className="text-muted-foreground text-sm">per month</span>
                    </p>
                )}
                <ul className="mt-6 space-y-2.5 flex-1">
                    {PLAN_FEATURES.map((feature) => (
                        <li key={feature} className="flex items-start gap-2 text-sm text-foreground/90">
                            <Check className="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
                            {feature}
                        </li>
                    ))}
                </ul>
                <Link href="/register" className="mt-8 text-center btn-pill-solid">
                    {TRIAL_CTA}
                </Link>
                <p className="mt-3 text-center text-xs text-muted-foreground">{TRIAL_LABEL}. No card required to start.</p>
            </article>
        </div>
    );
}
