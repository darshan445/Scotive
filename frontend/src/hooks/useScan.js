import { useCallback, useEffect, useState } from "react";
import { api, extractError, unwrapData } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

export function useLedger(shouldFetch = true) {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/v1/ledger");
            const ledger = unwrapData(data);
            setData(ledger);
            return ledger;
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
