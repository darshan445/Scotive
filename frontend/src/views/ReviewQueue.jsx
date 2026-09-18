"use client";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";

export default function ReviewQueuePage() {
    return (
        <AppShell testId="review-page" width="3xl" mainClassName="py-10 md:py-14">
            <div className="eyebrow mb-2">Review</div>
            <h1 className="type-display text-3xl md:text-4xl">Nothing in a separate queue</h1>
            <p className="type-body mt-3 text-sm text-muted-foreground max-w-xl">
                Firm and Final drafts, broken promises, and invoices that need a reply now live on Home.
                Scotive pauses chasing when a client talks back — you review those from the same list.
            </p>
            <Button asChild className="mt-6" data-testid="review-go-home">
                <Link href="/dashboard">Go to Home</Link>
            </Button>
        </AppShell>
    );
}
