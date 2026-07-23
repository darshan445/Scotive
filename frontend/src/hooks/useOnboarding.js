import { useCallback, useEffect, useRef, useState } from "react";
import { api, extractError } from "@/lib/api";

const POLL_MS = 1500;

function needsOnboardingPoll(data) {
    if (!data) return false;
    if (data.phase === "preparing" || data.phase === "scanning") return true;
    const review = data.seed_review;
    if (review?.seed_running || review?.status === "scanning" || review?.status === "waiting") {
        return true;
    }
    const pipe = data.qbo_pipeline;
    if (pipe?.status === "queued" || pipe?.status === "running") {
        return true;
    }
    return false;
}

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

    const refreshRef = useRef(refresh);
    refreshRef.current = refresh;
    const fetchCandidatesRef = useRef(fetchCandidates);
    fetchCandidatesRef.current = fetchCandidates;

    const startPollingStable = useCallback(() => {
        stopPolling();
        pollRef.current = setInterval(async () => {
            const data = await refreshRef.current();
            if (data?.phase === "curating" || data?.phase === "scanning") {
                fetchCandidatesRef.current();
            }
            if (!needsOnboardingPoll(data)) {
                stopPolling();
            }
        }, POLL_MS);
    }, [stopPolling]);

    const startSeed = useCallback(async () => {
        try {
            await api.post("/seed/start");
            const data = await refresh();
            if (needsOnboardingPoll(data)) {
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
            setCandidates(null);
            await refresh();
            return { ok: true, data };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [refresh, stopPolling]);

    const discardSeedReview = useCallback(async () => {
        try {
            const { data } = await api.post("/seed/review/discard");
            stopPolling();
            setCandidates(null);
            await refresh();
            return { ok: true, data };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [refresh, stopPolling]);

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
        if (state?.phase === "curating") {
            fetchCandidates();
        }
        if (needsOnboardingPoll(state)) {
            startPollingStable();
        } else if (state?.phase && state.phase !== "curating") {
            const pipe = state?.qbo_pipeline;
            const pipeBusy = pipe?.status === "queued" || pipe?.status === "running";
            if (!state?.seed_review?.seed_running && state?.seed_review?.status !== "scanning" && !pipeBusy) {
                stopPolling();
            }
        }
    }, [state, fetchCandidates, startPollingStable, stopPolling]);

    return {
        state,
        candidates,
        error,
        refresh,
        fetchCandidates,
        startSeed,
        confirmCuration,
        discardSeedReview,
    };
}
