import { useCallback, useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

const linkBase = "px-3 py-1.5 rounded-md text-sm font-medium transition-colors";

export function TopNav() {
    const { user, logout } = useAuth();
    const [reviewCount, setReviewCount] = useState(0);

    const loadReviewCount = useCallback(async () => {
        try {
            const { data } = await api.get("/review-queue");
            setReviewCount(data.count || 0);
        } catch {
            /* ignore */
        }
    }, []);

    useEffect(() => {
        loadReviewCount();
    }, [loadReviewCount]);

    useWorkspaceRefreshEffect(loadReviewCount);

    return (
        <header className="border-b border-border bg-card/90 backdrop-blur-md sticky top-0 z-30 shadow-sm">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <div className="flex items-center gap-8">
                    <BrandMark to="/dashboard" />
                    <nav className="hidden md:flex items-center gap-1">
                        <NavLink to="/dashboard" className={({ isActive }) => `${linkBase} ${isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`} data-testid="nav-dashboard">Dashboard</NavLink>
                        <NavLink to="/clients" className={({ isActive }) => `${linkBase} ${isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`} data-testid="nav-clients">Clients</NavLink>
                        <NavLink to="/review" className={({ isActive }) => `${linkBase} relative ${isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`} data-testid="nav-review">
                            Review
                            {reviewCount > 0 ? (
                                <span className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-amber-100 text-amber-800 text-[10px] font-mono px-1" data-testid="nav-review-badge">
                                    {reviewCount}
                                </span>
                            ) : null}
                        </NavLink>
                        <NavLink to="/settings" className={({ isActive }) => `${linkBase} ${isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`} data-testid="nav-settings">Settings</NavLink>
                    </nav>
                </div>
                <div className="flex items-center gap-4">
                    <div className="hidden sm:flex flex-col items-end leading-tight">
                        <span className="text-xs text-muted-foreground">Signed in</span>
                        <span className="text-sm font-medium" data-testid="nav-user-email">{user?.email}</span>
                    </div>
                    <Button variant="outline" size="sm" onClick={logout} className="rounded-md" data-testid="nav-logout-button">
                        <LogOut className="w-4 h-4 mr-1.5" /> Sign out
                    </Button>
                </div>
            </div>
        </header>
    );
}
