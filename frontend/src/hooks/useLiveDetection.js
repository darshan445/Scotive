import { useCallback, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

const POLL_MS =
    Number(process.env.NEXT_PUBLIC_SYNC_STATE_POLL_MS || process.env.VITE_SYNC_STATE_POLL_MS) ||
    120_000;

/**
 * Polls sync-state for new invoice detections (from hourly / manual sync).
 * Does not run a separate detect job — Sync now and the background loop share one job.
 */
export function useLiveDetection({ enabled, onDetected, onDueDatePrompt, onFollowUpPrompt }) {
    const shownRef = useRef(new Set());
    const promptRef = useRef(new Set());
    const onDetectedRef = useRef(onDetected);
    const onDueDatePromptRef = useRef(onDueDatePrompt);
    const onFollowUpPromptRef = useRef(onFollowUpPrompt);
    onDetectedRef.current = onDetected;
    onDueDatePromptRef.current = onDueDatePrompt;
    onFollowUpPromptRef.current = onFollowUpPrompt;

    const showUnread = useCallback((items) => {
        for (const inv of items || []) {
            const key = inv.source_message_id || inv.invoice_id;
            if (!key || shownRef.current.has(key)) continue;
            shownRef.current.add(key);
            onDetectedRef.current?.(inv);
        }
    }, []);

    const showDuePrompts = useCallback((items) => {
        for (const p of items || []) {
            const key = p.invoice_id;
            if (!key || promptRef.current.has(`due:${key}`)) continue;
            promptRef.current.add(`due:${key}`);
            onDueDatePromptRef.current?.(p);
        }
    }, []);

    const showFollowUpPrompts = useCallback((items) => {
        for (const p of items || []) {
            const key = p.invoice_id;
            if (!key || promptRef.current.has(`fu:${key}`)) continue;
            promptRef.current.add(`fu:${key}`);
            onFollowUpPromptRef.current?.(p);
        }
    }, []);

    const poll = useCallback(async () => {
        if (!enabled || document.hidden) return;
        try {
            const { data: state } = await api.get("/scan/sync-state");
            showUnread(state?.unread_detections);
            showDuePrompts(state?.pending_due_date_prompts);
            showFollowUpPrompts(state?.pending_followup_prompts);
        } catch {
            /* silent — will retry on next interval */
        }
    }, [enabled, showUnread, showDuePrompts, showFollowUpPrompts]);

    useEffect(() => {
        if (!enabled) return undefined;
        poll();
        const t = setInterval(poll, POLL_MS);
        const onVis = () => {
            if (!document.hidden) poll();
        };
        document.addEventListener("visibilitychange", onVis);
        return () => {
            clearInterval(t);
            document.removeEventListener("visibilitychange", onVis);
        };
    }, [enabled, poll]);

    useWorkspaceRefreshEffect(() => {
        if (enabled) poll();
    });

    const ackAll = useCallback(async () => {
        try {
            await api.post("/sync/detections/ack", {});
        } catch {
            /* ignore */
        }
    }, []);

    return { poll, ackAll };
}
