import axios from "axios";

const BACKEND_URL =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.REACT_APP_BACKEND_URL ||
    "";

export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API_BASE,
    withCredentials: true,
    timeout: 20000,
});

/** Sync now / QBO import — Gmail + model can take well over the default 20s. */
export const LONG_JOB_TIMEOUT_MS = 180_000;

export function isTimeoutError(err) {
    if (err?.response) return false;
    const code = err?.code || "";
    if (code === "ECONNABORTED") return true;
    return /timeout/i.test(err?.message || "");
}

export function formatApiErrorDetail(detail) {
    if (detail == null) return "Something went wrong. Please try again.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
            .filter(Boolean)
            .join(" ");
    }
    if (detail && typeof detail.msg === "string") return detail.msg;
    return String(detail);
}

export function extractError(err) {
    if (!err?.response) {
        if (isTimeoutError(err)) {
            return "That's taking longer than expected. Refresh in a moment — the work may still finish.";
        }
        const code = err?.code || "";
        if (
            code === "ERR_NETWORK" ||
            code === "ECONNRESET" ||
            /network|connection/i.test(err?.message || "")
        ) {
            return "Can't reach the server. Check that the API is running, then try again.";
        }
    }
    return formatApiErrorDetail(err?.response?.data?.detail) || err?.message || "Unexpected error";
}
