import { useCallback, useEffect, useRef, useState } from "react";
import { api, extractError } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

export function useScan() {
    const [state, setState] = useState(null); // {has_job, status, phase, counts, ...}
    const [error, setError] = useState("");
    const pollRef = useRef(null);

    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    }, []);

    const fetchStatus = useCallback(async () => {
        try {
            const { data } = await api.get("/scan/status");
            setState(data);
            if (data.has_job && (data.status === "complete" || data.status === "error")) {
                stopPolling();
            }
            return data;
        } catch (e) {
            setError(extractError(e));
            return null;
        }
    }, [stopPolling]);

    const startPolling = useCallback(() => {
        stopPolling();
        pollRef.current = setInterval(fetchStatus, 1500);
    }, [fetchStatus, stopPolling]);

    useEffect(() => {
        fetchStatus().then((data) => {
            if (data?.has_job && (data.status === "queued" || data.status === "running")) {
                startPolling();
            }
        });
        return stopPolling;
    }, [fetchStatus, startPolling, stopPolling]);

    const startScan = useCallback(async (months) => {
        try {
            const body = months != null ? { months } : {};
            await api.post("/scan/start", body);
            await fetchStatus();
            startPolling();
            return { ok: true };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [fetchStatus, startPolling]);

    return { state, error, startScan, refresh: fetchStatus };
}

export function useLedger(shouldFetch = true) {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/ledger");
            setData(data);
            return data;
        } catch (e) {
            setError(extractError(e));
            return null;
        }
    }, []);

    useEffect(() => {
        if (shouldFetch) refresh();
    }, [shouldFetch, refresh]);

    useWorkspaceRefreshEffect(() => {
        if (shouldFetch) refresh();
    });

    return { data, error, refresh };
}
