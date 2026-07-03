import { useCallback, useEffect, useState } from "react";
import { api, extractError } from "@/lib/api";

// status shape from backend GmailStatus
export function useGmailConnection() {
    const [status, setStatus] = useState(null); // null = loading
    const [error, setError] = useState("");

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/gmail/status");
            setStatus(data);
            setError("");
            return data;
        } catch (e) {
            setError(extractError(e));
            setStatus({ connected: false, status: "disconnected", can_send: false, email: null });
            return null;
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const startConnect = useCallback(async () => {
        try {
            const { data } = await api.get("/gmail/oauth/start");
            window.location.href = data.authorization_url;
        } catch (e) {
            setError(extractError(e));
        }
    }, []);

    const disconnect = useCallback(async () => {
        try {
            await api.post("/gmail/disconnect");
            await refresh();
            return { ok: true };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [refresh]);

    return { status, error, refresh, startConnect, disconnect };
}
