import { useCallback, useEffect, useState } from "react";
import { api, extractError } from "@/lib/api";

export function useReceipts(shouldFetch = true) {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/receipts");
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

    return { data, error, refresh };
}
