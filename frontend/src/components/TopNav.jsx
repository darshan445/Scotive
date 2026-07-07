import { useCallback, useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { NavLink } from "react-router-dom";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

const linkBase = "px-3.5 py-2 rounded-full text-sm font-medium transition-colors";

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
        <header className="border-b border-border/70 bg-background/85 backdrop-blur-md sticky top-0 z-30">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <div className="flex items-center gap-8">
                    <BrandMark to="/dashboard" />
                    <nav className="hidden md:flex items-center gap-1 bg-muted/60 rounded-full p-1">
                        <NavLink to="/dashboard" className={({ isActive }) => `${linkBase} ${isActive ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} data-testid="nav-dashboard">Home</NavLink>
                        <NavLink to="/clients" className={({ isActive }) => `${linkBase} ${isActive ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} data-testid="nav-clients">Clients</NavLink>
                        <NavLink to="/review" className={({ isActive }) => `${linkBase} relative ${isActive ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} data-testid="nav-review">
                            Review
                            {reviewCount > 0 ? (
                                <span className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-accent text-accent-foreground text-[10px] font-semibold px-1" data-testid="nav-review-badge">
                                    {reviewCount}
                                </span>
                            ) : null}
                        </NavLink>
                        <NavLink to="/settings" className={({ isActive }) => `${linkBase} ${isActive ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} data-testid="nav-settings">Settings</NavLink>
                    </nav>
                </div>
                <div className="flex items-center gap-3">
                    <div className="hidden sm:flex items-center gap-2.5">
                        <span className="w-8 h-8 rounded-full bg-primary/10 text-primary text-xs font-heading font-bold inline-flex items-center justify-center uppercase">
                            {(user?.email || "?").slice(0, 1)}
                        </span>
                        <span className="text-sm font-medium max-w-[180px] truncate" data-testid="nav-user-email">{user?.email}</span>
                    </div>
                    <Button variant="ghost" size="sm" onClick={logout} className="rounded-full text-muted-foreground hover:text-foreground" data-testid="nav-logout-button">
                        <LogOut className="w-4 h-4 mr-1.5" /> Sign out
                    </Button>
                </div>
            </div>
        </header>
    );
}
