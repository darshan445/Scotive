import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function ProtectedRoute({ children }) {
    const { user, isLoading } = useAuth();
    const location = useLocation();

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background" data-testid="auth-loading">
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                    <div className="w-1.5 h-1.5 rounded-full bg-foreground animate-pulse" />
                    <span className="text-xs font-mono uppercase tracking-[0.2em]">Loading</span>
                </div>
            </div>
        );
    }

    if (!user) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return children;
}

export function GuestRoute({ children }) {
    const { user, isLoading } = useAuth();
    if (isLoading) return null;
    if (user) return <Navigate to="/dashboard" replace />;
    return children;
}
