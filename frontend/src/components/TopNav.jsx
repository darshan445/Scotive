"use client";
import { useCallback, useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

const linkBase = "px-3 py-2 rounded-md text-sm font-medium transition-colors";

function NavItem({ href, children, testId, className = "" }) {
    const pathname = usePathname();
    const active = pathname === href || (href !== "/dashboard" && pathname?.startsWith(href));
    return (
        <Link
            href={href}
            className={`${linkBase} ${active ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted"} ${className}`}
            data-testid={testId}
        >
            {children}
        </Link>
    );
}

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
        <header className="border-b border-border bg-background/95 backdrop-blur-sm sticky top-0 z-30">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <div className="flex items-center gap-6">
                    <BrandMark to="/dashboard" />
                    <nav className="hidden md:flex items-center gap-1" aria-label="App">
                        <NavItem href="/dashboard" testId="nav-dashboard">Home</NavItem>
                        <NavItem href="/clients" testId="nav-clients">Clients</NavItem>
                        <NavItem href="/review" testId="nav-review" className="relative">
                            Review
                            {reviewCount > 0 ? (
                                <span className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-md bg-primary text-primary-foreground text-[10px] font-semibold px-1" data-testid="nav-review-badge">
                                    {reviewCount}
                                </span>
                            ) : null}
                        </NavItem>
                        <NavItem href="/settings" testId="nav-settings">Settings</NavItem>
                    </nav>
                </div>
                <div className="flex items-center gap-3">
                    <div className="hidden sm:flex items-center gap-2.5">
                        <span className="w-8 h-8 rounded-md bg-primary/10 text-primary text-xs type-title inline-flex items-center justify-center uppercase">
                            {(user?.email || "?").slice(0, 1)}
                        </span>
                        <span className="text-sm font-medium max-w-[180px] truncate" data-testid="nav-user-email">{user?.email}</span>
                    </div>
                    <Button variant="ghost" size="sm" onClick={logout} className="rounded-md text-muted-foreground hover:text-foreground" data-testid="nav-logout-button">
                        <LogOut className="w-4 h-4 mr-1.5" /> Sign out
                    </Button>
                </div>
            </div>
        </header>
    );
}
