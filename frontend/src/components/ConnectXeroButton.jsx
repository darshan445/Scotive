import { ArrowRight } from "lucide-react";
import { useXeroConnection } from "@/hooks/useXeroConnection";
import { Button } from "@/components/ui/button";
import { XeroMark } from "@/components/XeroMark";

export function ConnectXeroButton({
    testId = "connect-xero-button",
    label = "Connect Xero",
    variant = "primary",
    compact = false,
}) {
    const { startConnect, error } = useXeroConnection();

    const base =
        "group relative inline-flex items-center gap-3 rounded-full pl-2 pr-6 py-2 font-semibold text-base transition-all shadow-sm active:scale-[0.98]";
    const styles =
        variant === "primary"
            ? "bg-foreground text-background hover:bg-foreground/90 hover:pr-7"
            : "bg-card text-foreground border border-border hover:border-foreground/40 hover:pr-7";

    return (
        <div className="flex flex-col items-start gap-1">
            {compact ? (
                <Button
                    type="button"
                    size="sm"
                    variant={variant === "secondary" ? "outline" : "default"}
                    className="rounded-full"
                    onClick={startConnect}
                    data-testid={testId}
                >
                    Connect
                    <ArrowRight className="w-3.5 h-3.5" />
                </Button>
            ) : (
                <button
                    type="button"
                    onClick={startConnect}
                    className={`${base} ${styles}`}
                    data-testid={testId}
                >
                    <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-background border border-border">
                        <XeroMark />
                    </span>
                    {label}
                    <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
                </button>
            )}
            {error ? (
                <p className="text-xs text-red-600 max-w-xs" data-testid="connect-xero-error">{error}</p>
            ) : null}
        </div>
    );
}
