import { ArrowRight } from "lucide-react";
import { SiQuickbooks } from "react-icons/si";
import { useQboConnection } from "@/hooks/useQboConnection";

export function ConnectQboButton({
    testId = "connect-qbo-button",
    label = "Connect QuickBooks",
    variant = "primary",
}) {
    const { startConnect, error } = useQboConnection();

    const base =
        "group relative inline-flex items-center gap-3 rounded-full pl-2 pr-6 py-2 font-semibold text-base transition-all shadow-sm active:scale-[0.98]";
    const styles =
        variant === "primary"
            ? "bg-foreground text-background hover:bg-foreground/90 hover:pr-7"
            : "bg-card text-foreground border border-border hover:border-foreground/40 hover:pr-7";

    return (
        <div className="flex flex-col items-start gap-1">
            <button
                type="button"
                onClick={startConnect}
                className={`${base} ${styles}`}
                data-testid={testId}
            >
                <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-background border border-border">
                    <SiQuickbooks className="w-5 h-5 text-[#2CA01C]" />
                </span>
                {label}
                <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
            </button>
            {error ? (
                <p className="text-xs text-red-600 max-w-xs" data-testid="connect-qbo-error">{error}</p>
            ) : null}
        </div>
    );
}
