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
        const code = err?.code || "";
        if (
            code === "ECONNABORTED" ||
            code === "ERR_NETWORK" ||
            code === "ECONNRESET" ||
            /timeout|network|connection/i.test(err?.message || "")
        ) {
            return "Can't reach the server. Check that the API is running, then try again.";
        }
    }
    return formatApiErrorDetail(err?.response?.data?.detail) || err?.message || "Unexpected error";
}
