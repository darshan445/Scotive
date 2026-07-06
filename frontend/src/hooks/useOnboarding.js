import { useCallback, useEffect, useRef, useState } from "react";
import { api, extractError } from "@/lib/api";

const POLL_MS = 1500;

export function useOnboarding({ enabled = true } = {}) {
    const [state, setState] = useState(null);
    const [candidates, setCandidates] = useState(null);
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

    // Keep polling callback on latest refresh without re-creating interval each render
    const refreshRef = useRef(refresh);
    refreshRef.current = refresh;

    const startPollingStable = useCallback(() => {
        stopPolling();
        pollRef.current = setInterval(() => {
            refreshRef.current();
        }, POLL_MS);
    }, [stopPolling]);

    const startSeed = useCallback(async () => {
        try {
            await api.post("/seed/start");
            const data = await refresh();
            if (data?.phase === "scanning") {
                startPollingStable();
            }
            return { ok: true, data };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [refresh, startPollingStable]);

    const confirmCuration = useCallback(async (candidateIds, trackNone = false, dueDates = {}) => {
        try {
            const { data } = await api.post("/seed/confirm", {
                candidate_ids: candidateIds,
                track_none: trackNone,
                due_dates: dueDates,
            });
            stopPolling();
            await refresh();
            return { ok: true, data };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [refresh, stopPolling]);

    const fetchCandidates = useCallback(async () => {
        try {
            const { data } = await api.get("/seed/candidates");
            setCandidates(data.candidates || []);
            return data.candidates || [];
        } catch (e) {
            setError(extractError(e));
            return [];
        }
    }, []);

    // Load state when Gmail becomes connected
    useEffect(() => {
        if (!enabled) {
            stopPolling();
            return undefined;
        }
        refresh().then((data) => {
            if (data?.phase === "scanning") {
                startPollingStable();
            }
        });
        return stopPolling;
    }, [enabled, refresh, startPollingStable, stopPolling]);

    useEffect(() => {
        if (state?.phase === "curating") {
            fetchCandidates();
        }
    }, [state?.phase, fetchCandidates]);

    // Stop polling once scan finishes — but not while state is still loading (null)
    useEffect(() => {
        if (!state?.phase) return;
        if (state.phase !== "scanning") {
            stopPolling();
        }
    }, [state?.phase, stopPolling]);

    return {
        state,
        candidates,
        error,
        refresh,
        fetchCandidates,
        startSeed,
        confirmCuration,
    };
}
