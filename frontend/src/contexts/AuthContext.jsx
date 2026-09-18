"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, extractError, setAuthToken } from "@/lib/api";

const AuthContext = createContext(null);

function sessionFrom(payload) {
    const data = payload?.data ?? payload;
    const user = data?.user ?? null;
    const token = data?.token;
    if (token) setAuthToken(token);
    return user;
}

export function AuthProvider({ children }) {
    // null = checking, false = anon, object = user
    const [user, setUser] = useState(null);

    const fetchMe = useCallback(async () => {
        try {
            const { data } = await api.get("/v1/auth/me");
            const next = sessionFrom(data);
            setUser(next || false);
            return next;
        } catch (_e) {
            setAuthToken(null);
            setUser(false);
            return null;
        }
    }, []);

    useEffect(() => {
        fetchMe();
    }, [fetchMe]);

    const login = useCallback(async (email, password) => {
        try {
            const { data } = await api.post("/v1/auth/sign-in", { email, password });
            const next = sessionFrom(data);
            setUser(next);
            return { ok: true, user: next };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const register = useCallback(async (email, password, name, timezone) => {
        try {
            const body = { email, password, name };
            if (timezone) body.timezone = timezone;
            const { data } = await api.post("/v1/auth/sign-up", body);
            const next = sessionFrom(data);
            setUser(next);
            return { ok: true, user: next };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const logout = useCallback(async () => {
        try {
            await api.delete("/v1/auth/sign-out");
        } catch (_e) {
            /* ignore */
        }
        setAuthToken(null);
        setUser(false);
    }, []);

    const forgotPassword = useCallback(async (email) => {
        try {
            const { data } = await api.post("/v1/auth/forgot-password", { email });
            return { ok: true, message: data?.data?.message || data?.message };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const resetPassword = useCallback(async (token, password) => {
        try {
            await api.post("/v1/auth/reset-password", { token, password });
            return { ok: true };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const value = {
        user,
        isLoading: user === null,
        isAuthenticated: !!user && user !== false,
        login,
        register,
        logout,
        forgotPassword,
        resetPassword,
        refresh: fetchMe,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
