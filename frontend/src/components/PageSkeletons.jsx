import { Skeleton } from "@/components/ui/skeleton";

function PageHeaderSkeleton({ subtitle = true, testId }) {
    return (
        <div data-testid={testId}>
            <Skeleton className="h-3 w-20 mb-3" />
            <Skeleton className="h-9 w-64 max-w-full md:h-10 md:w-80" />
            {subtitle ? <Skeleton className="mt-3 h-4 w-72 max-w-full" /> : null}
        </div>
    );
}

export function StatsStripSkeleton() {
    return (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="stats-skeleton">
            {[0, 1, 2].map((i) => (
                <div key={i} className="surface-card p-5 flex flex-col gap-2">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="h-8 w-28" />
                    <Skeleton className="h-3 w-36" />
                </div>
            ))}
        </div>
    );
}

export function TodayCardSkeleton() {
    return (
        <div className="surface-card overflow-hidden" data-testid="today-card-skeleton">
            <div className="px-6 py-5 border-b border-border flex items-center justify-between">
                <div className="space-y-2">
                    <Skeleton className="h-6 w-40" />
                    <Skeleton className="h-3 w-48" />
                </div>
                <Skeleton className="h-9 w-9 rounded-full" />
            </div>
            <ul className="divide-y divide-border">
                {[0, 1, 2].map((i) => (
                    <li key={i} className="px-6 py-4 flex items-start gap-3">
                        <Skeleton className="mt-0.5 h-4 w-4 rounded flex-shrink-0" />
                        <div className="min-w-0 flex-1 space-y-2">
                            <div className="flex flex-wrap gap-2">
                                <Skeleton className="h-4 w-32" />
                                <Skeleton className="h-4 w-16" />
                                <Skeleton className="h-4 w-20 rounded-full" />
                            </div>
                            <Skeleton className="h-4 w-3/4 max-w-md" />
                            <Skeleton className="h-3 w-40" />
                        </div>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export function LedgerCardSkeleton() {
    return (
        <div className="space-y-6" data-testid="ledger-skeleton">
            <div className="surface-card p-6 md:p-7 space-y-4">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-10 w-40" />
                <Skeleton className="h-4 w-56" />
            </div>
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
                <div className="px-4 py-3 border-b border-border bg-muted/40 flex gap-4">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-3 w-16" />
                    <Skeleton className="h-3 w-24 ml-auto" />
                </div>
                {[0, 1, 2, 3, 4].map((i) => (
                    <div key={i} className="px-4 py-4 border-b border-border/60 flex items-center gap-4">
                        <div className="min-w-0 flex-1 space-y-2">
                            <Skeleton className="h-4 w-40" />
                            <Skeleton className="h-3 w-56 max-w-full" />
                        </div>
                        <Skeleton className="h-4 w-16 flex-shrink-0" />
                        <Skeleton className="h-5 w-20 rounded-full flex-shrink-0" />
                    </div>
                ))}
            </div>
        </div>
    );
}

export function DashboardSkeleton() {
    return (
        <div className="py-8 md:py-12 space-y-6" data-testid="dashboard-loading">
            <PageHeaderSkeleton />
            <StatsStripSkeleton />
            <TodayCardSkeleton />
            <div className="flex gap-2">
                <Skeleton className="h-10 w-24 rounded-full" />
                <Skeleton className="h-10 w-20 rounded-full" />
            </div>
            <LedgerCardSkeleton />
        </div>
    );
}

export function DashboardContentSkeleton() {
    // Stats + ledger shell only — TodayCard may stay empty, so don't imply it.
    return (
        <div className="space-y-6" data-testid="dashboard-content-skeleton">
            <StatsStripSkeleton />
            <div className="flex gap-2">
                <Skeleton className="h-10 w-24 rounded-full" />
                <Skeleton className="h-10 w-20 rounded-full" />
            </div>
            <LedgerCardSkeleton />
        </div>
    );
}

export function ClientsTableSkeleton() {
    return (
        <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="clients-skeleton">
            <div className="px-4 py-3 border-b border-border bg-muted/40 flex gap-4">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-3 w-24 ml-auto" />
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-3 w-24" />
            </div>
            {[0, 1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="px-4 py-3 border-b border-border/60 flex items-center gap-4">
                    <div className="min-w-0 flex-1 space-y-1.5">
                        <Skeleton className="h-4 w-36" />
                        <Skeleton className="h-3 w-48" />
                    </div>
                    <Skeleton className="h-4 w-20" />
                    <Skeleton className="h-4 w-8" />
                    <Skeleton className="h-4 w-24" />
                </div>
            ))}
        </div>
    );
}

export function ClientDetailSkeleton() {
    return (
        <div className="space-y-8" data-testid="client-detail-skeleton">
            <div>
                <Skeleton className="h-3 w-16 mb-3" />
                <Skeleton className="h-9 w-56 max-w-full md:h-10" />
                <Skeleton className="mt-2 h-4 w-48" />
                <div className="mt-6 surface-card p-6 space-y-2">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="h-10 w-36" />
                </div>
            </div>
            <div>
                <Skeleton className="h-6 w-44 mb-3" />
                <div className="rounded-2xl border border-border bg-card p-6 space-y-5">
                    <Skeleton className="h-6 w-28 rounded-full" />
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                        {[0, 1, 2].map((i) => (
                            <div key={i} className="space-y-2">
                                <Skeleton className="h-3 w-24" />
                                <Skeleton className="h-8 w-16" />
                                <Skeleton className="h-3 w-32" />
                            </div>
                        ))}
                    </div>
                </div>
            </div>
            <div>
                <Skeleton className="h-6 w-48 mb-3" />
                <div className="rounded-2xl border border-border bg-card divide-y divide-border">
                    {[0, 1].map((i) => (
                        <div key={i} className="px-4 py-3 flex justify-between">
                            <Skeleton className="h-4 w-48" />
                            <Skeleton className="h-3 w-12" />
                        </div>
                    ))}
                </div>
            </div>
            <div>
                <Skeleton className="h-6 w-24 mb-3" />
                <div className="space-y-3">
                    {[0, 1, 2].map((i) => (
                        <div key={i} className="rounded-xl border border-border bg-card p-4 space-y-2">
                            <div className="flex justify-between gap-2">
                                <Skeleton className="h-4 w-48" />
                                <Skeleton className="h-4 w-16" />
                            </div>
                            <Skeleton className="h-3 w-32" />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

export function ReviewQueueSkeleton() {
    return (
        <ul className="space-y-4" data-testid="review-skeleton">
            {[0, 1, 2].map((i) => (
                <li key={i} className="rounded-2xl border border-border bg-card p-5 space-y-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-2 min-w-0 flex-1">
                            <Skeleton className="h-5 w-40" />
                            <Skeleton className="h-3 w-64 max-w-full" />
                        </div>
                        <Skeleton className="h-6 w-24 rounded-full" />
                    </div>
                    <Skeleton className="h-16 w-full rounded-xl" />
                    <div className="grid grid-cols-2 gap-3">
                        <Skeleton className="h-9 w-full" />
                        <Skeleton className="h-9 w-full" />
                    </div>
                    <div className="flex gap-2">
                        <Skeleton className="h-9 w-24" />
                        <Skeleton className="h-9 w-24" />
                    </div>
                </li>
            ))}
        </ul>
    );
}

export function SettingsSkeleton() {
    return (
        <div className="space-y-10" data-testid="settings-skeleton">
            <PageHeaderSkeleton />
            {[0, 1, 2].map((i) => (
                <div key={i} className="space-y-4">
                    <Skeleton className="h-5 w-40" />
                    <div className="rounded-2xl border border-border bg-card p-6 space-y-4">
                        <Skeleton className="h-4 w-full max-w-md" />
                        <Skeleton className="h-10 w-full max-w-sm" />
                        <Skeleton className="h-4 w-48" />
                        <Skeleton className="h-10 w-28" />
                    </div>
                </div>
            ))}
        </div>
    );
}

export function AuthLoadingSkeleton() {
    return (
        <div className="min-h-screen bg-background flex flex-col" data-testid="auth-loading">
            <div className="border-b border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
                    <Skeleton className="h-5 w-24" />
                    <div className="flex gap-3">
                        <Skeleton className="h-4 w-16" />
                        <Skeleton className="h-4 w-16" />
                    </div>
                </div>
            </div>
            <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <DashboardSkeleton />
            </main>
            <footer className="border-t border-border mt-auto">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-wrap justify-between items-center gap-3">
                    <Skeleton className="h-3 w-28" />
                    <Skeleton className="h-3 w-36" />
                </div>
            </footer>
        </div>
    );
}
