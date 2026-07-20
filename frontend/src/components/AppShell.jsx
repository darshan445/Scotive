import { TopNav } from "@/components/TopNav";
import { AppFooter } from "@/components/AppFooter";
import { cn } from "@/lib/utils";

const WIDTH_CLASS = {
    "7xl": "max-w-7xl",
    "5xl": "max-w-5xl",
    "3xl": "max-w-3xl",
    full: "max-w-none",
};

/**
 * Full-viewport page chrome: TopNav + growing main + footer pinned to the
 * bottom when content is short.
 */
export function AppShell({
    children,
    testId,
    width = "7xl",
    mainClassName = "",
    showFooter = true,
    afterMain = null,
}) {
    return (
        <div
            className="min-h-screen bg-background text-foreground flex flex-col"
            data-testid={testId}
        >
            <TopNav />
            <main
                className={cn(
                    "flex-1 w-full mx-auto px-4 sm:px-6 lg:px-8",
                    WIDTH_CLASS[width] || WIDTH_CLASS["7xl"],
                    mainClassName,
                )}
            >
                {children}
            </main>
            {afterMain}
            {showFooter ? <AppFooter /> : null}
        </div>
    );
}
