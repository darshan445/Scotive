import { LogOut } from "lucide-react";
import { Link } from "react-router-dom";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";

export function TopNav() {
    const { user, logout } = useAuth();
    return (
        <header className="border-b border-border bg-background/80 backdrop-blur-sm sticky top-0 z-30">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <div className="flex items-center gap-8">
                    <BrandMark to="/dashboard" />
                    <nav className="hidden md:flex items-center gap-1 text-sm">
                        <Link
                            to="/dashboard"
                            className="px-3 py-1.5 rounded-md text-foreground font-medium hover:bg-muted transition-colors"
                            data-testid="nav-dashboard"
                        >
                            Dashboard
                        </Link>
                        <span
                            className="px-3 py-1.5 rounded-md text-muted-foreground/50 font-medium cursor-not-allowed"
                            title="Available after you connect Gmail"
                            data-testid="nav-ledger-disabled"
                        >
                            Ledger
                        </span>
                        <span
                            className="px-3 py-1.5 rounded-md text-muted-foreground/50 font-medium cursor-not-allowed"
                            title="Available after you connect Gmail"
                            data-testid="nav-clients-disabled"
                        >
                            Clients
                        </span>
                    </nav>
                </div>
                <div className="flex items-center gap-4">
                    <div className="hidden sm:flex flex-col items-end leading-tight">
                        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Signed in</span>
                        <span className="text-sm font-medium" data-testid="nav-user-email">{user?.email}</span>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={logout}
                        className="rounded-md"
                        data-testid="nav-logout-button"
                    >
                        <LogOut className="w-4 h-4 mr-1.5" />
                        Sign out
                    </Button>
                </div>
            </div>
        </header>
    );
}
