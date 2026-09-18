import { useCallback, useEffect, useState } from "react";
import { api, extractError, unwrapData } from "@/lib/api";

// status shape from backend GmailStatus (mailbox — Gmail or Outlook)
export function useGmailConnection() {
    const [status, setStatus] = useState(null); // null = loading
    const [error, setError] = useState("");

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/v1/gmail/status");
            const statusData = unwrapData(data);
            setStatus(statusData);
            setError("");
            return statusData;
        } catch (e) {
            setError(extractError(e));
            setStatus({ connected: false, status: "disconnected", can_send: false, email: null, provider: null });
            return null;
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const startConnect = useCallback(async (provider = "google") => {
        try {
            const p = provider === "outlook" ? "outlook" : "google";
            const { data } = await api.get("/v1/gmail/oauth/start", { params: { provider: p } });
            window.location.href = unwrapData(data).authorization_url;
        } catch (e) {
            setError(extractError(e));
        }
    }, []);

    const disconnect = useCallback(async (provider) => {
        try {
            const params = provider ? { provider } : undefined;
            await api.post("/v1/gmail/disconnect", null, { params });
            await refresh();
            return { ok: true };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, [refresh]);

    return { status, error, refresh, startConnect, disconnect };
}
