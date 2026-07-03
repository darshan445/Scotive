import { LogOut } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
    const { user, logout } = useAuth();

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="dashboard-root">
            <header className="border-b border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <BrandMark />
                    <div className="flex items-center gap-4">
                        <div className="hidden sm:flex flex-col items-end leading-tight">
                            <span className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">Signed in</span>
                            <span className="text-sm font-medium" data-testid="dashboard-user-email">{user?.email}</span>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={logout}
                            className="rounded-md"
                            data-testid="dashboard-logout-button"
                        >
                            <LogOut className="w-4 h-4 mr-1.5" />
                            Sign out
                        </Button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                <div className="max-w-2xl">
                    <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-4">
                        Feature 1 · Auth · Complete
                    </div>
                    <h1 className="font-heading font-black text-4xl md:text-5xl leading-[1.05] tracking-tight">
                        {`You're signed in`}{user?.name ? `, ${user.name.split(" ")[0]}` : ""}.
                    </h1>
                    <p className="mt-3 text-base text-muted-foreground leading-relaxed">
                        {`The empty-state dashboard with the "Connect Gmail" CTA lands here next. Once you approve Feature 1, we'll build it.`}
                    </p>
                </div>
            </main>
        </div>
    );
}
