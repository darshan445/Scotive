import axios from "axios";

const BACKEND_URL =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.REACT_APP_BACKEND_URL ||
    "";

export const API_BASE = `${BACKEND_URL}/api`;
const TOKEN_KEY = "scotive_token";

export function getAuthToken() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token) {
    if (typeof window === "undefined") return;
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
}

export const api = axios.create({
    baseURL: API_BASE,
    withCredentials: true,
    timeout: 20000,
});

api.interceptors.request.use((config) => {
    const token = getAuthToken();
    if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

api.interceptors.response.use(
    (response) => response,
    (error) => {
        const url = String(error?.config?.url || "");
        const isAuthAttempt = /\/v1\/auth\/(sign-in|sign-up)/.test(url);
        if (error?.response?.status === 401 && !isAuthAttempt) {
            setAuthToken(null);
        }
        return Promise.reject(error);
    }
);

/** Rails JSON envelope is `{ data: ... }`. Auth already unwraps; OAuth hooks use this. */
export function unwrapData(payload) {
    if (payload && typeof payload === "object" && Object.prototype.hasOwnProperty.call(payload, "data")) {
        return payload.data;
    }
    return payload;
}

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
            .map((e) => {
                if (!e) return "";
                if (typeof e === "string") return e;
                if (typeof e.detail === "string") return e.detail;
                if (typeof e.msg === "string") return e.msg;
                return JSON.stringify(e);
            })
            .filter(Boolean)
            .join(" ");
    }
    if (detail && typeof detail.detail === "string") return detail.detail;
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
    const data = err?.response?.data;
    if (Array.isArray(data?.errors) && data.errors.length) {
        return formatApiErrorDetail(data.errors);
    }
    return formatApiErrorDetail(data?.detail) || err?.message || "Unexpected error";
}
