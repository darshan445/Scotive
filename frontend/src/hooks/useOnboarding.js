import { useCallback, useEffect, useRef, useState } from "react";
import { api, extractError } from "@/lib/api";

const POLL_MS = 1500;

function needsOnboardingPoll(data) {
    // Pipeline progress is polled on the connect page via /qbo/pipeline-status.
    // Dashboard no longer shows a matching bar, so don't keep /onboarding/state hot.
    return Boolean(data?.phase === "connections" && data?.qbo_import_progress?.status === "running");
}

export function useOnboarding({ enabled = true } = {}) {
    const [state, setState] = useState(null);
    const [error, setError] = useState("");
    const pollRef = useRef(null);

    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    }, []);

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/onboarding/state");
            setState(data);
            return data;
        } catch (e) {
            setError(extractError(e));
            return null;
        }
    }, []);

    const refreshRef = useRef(refresh);
    refreshRef.current = refresh;

    const startPollingStable = useCallback(() => {
        stopPolling();
        pollRef.current = setInterval(async () => {
            const data = await refreshRef.current();
            if (!needsOnboardingPoll(data)) {
                stopPolling();
            }
        }, POLL_MS);
    }, [stopPolling]);

    useEffect(() => {
        if (!enabled) {
            stopPolling();
            return undefined;
        }
        refresh().then((data) => {
            if (needsOnboardingPoll(data)) {
                startPollingStable();
            }
        });
        return stopPolling;
    }, [enabled, refresh, startPollingStable, stopPolling]);

    useEffect(() => {
        if (needsOnboardingPoll(state)) {
            startPollingStable();
        } else if (state?.phase) {
            stopPolling();
        }
    }, [state, startPollingStable, stopPolling]);

    return {
        state,
        error,
        refresh,
    };
}
