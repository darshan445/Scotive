import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, extractError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    // null = checking, false = anon, object = user
    const [user, setUser] = useState(null);

    const fetchMe = useCallback(async () => {
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
            return data;
        } catch (_e) {
            setUser(false);
            return null;
        }
    }, []);

    useEffect(() => {
        fetchMe();
    }, [fetchMe]);

    const login = useCallback(async (email, password) => {
        try {
            const { data } = await api.post("/auth/login", { email, password });
            setUser(data);
            return { ok: true, user: data };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const register = useCallback(async (email, password, name, timezone) => {
        try {
            const body = { email, password, name };
            if (timezone) body.timezone = timezone;
            const { data } = await api.post("/auth/register", body);
            setUser(data);
            return { ok: true, user: data };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const logout = useCallback(async () => {
        try {
            await api.post("/auth/logout");
        } catch (_e) {
            /* ignore */
        }
        setUser(false);
    }, []);

    const forgotPassword = useCallback(async (email) => {
        try {
            const { data } = await api.post("/auth/forgot-password", { email });
            return { ok: true, message: data?.message };
        } catch (e) {
            return { ok: false, error: extractError(e) };
        }
    }, []);

    const resetPassword = useCallback(async (token, password) => {
        try {
            await api.post("/auth/reset-password", { token, password });
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
