import { useCallback } from "react";
import { notifyWorkspaceRefresh } from "@/lib/workspaceRefresh";

/**
 * Combine parent data hooks with a global refresh signal for child views
 * that keep their own fetch state (Today digest, chase queue, sync bar, …).
 */
export function useWorkspaceRefresh({ refreshLedger, refreshReceipts, refreshOnboarding } = {}) {
    const refreshAll = useCallback(async () => {
        notifyWorkspaceRefresh();
        await Promise.all([
            refreshLedger?.(),
            refreshReceipts?.(),
            refreshOnboarding?.(),
        ].filter(Boolean));
    }, [refreshLedger, refreshReceipts, refreshOnboarding]);

    return { refreshAll };
}

export { useWorkspaceRefreshEffect, notifyWorkspaceRefresh } from "@/lib/workspaceRefresh";
