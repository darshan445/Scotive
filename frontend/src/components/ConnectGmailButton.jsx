import { FcGoogle } from "react-icons/fc";
import { ArrowRight } from "lucide-react";
import { useGmailConnection } from "@/hooks/useGmailConnection";

export function ConnectGmailButton({
    testId = "connect-gmail-button",
    label = "Connect Gmail",
    variant = "primary",
}) {
    const { startConnect } = useGmailConnection();

    const base =
        "group relative inline-flex items-center gap-3 rounded-full pl-2 pr-6 py-2 font-semibold text-base transition-all shadow-sm active:scale-[0.98]";
    const styles =
        variant === "primary"
            ? "bg-foreground text-background hover:bg-foreground/90 hover:pr-7"
            : "bg-card text-foreground border border-border hover:border-foreground/40 hover:pr-7";

    return (
        <button
            type="button"
            onClick={startConnect}
            className={`${base} ${styles}`}
            data-testid={testId}
        >
            <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-background border border-border">
                <FcGoogle className="w-5 h-5" />
            </span>
            {label}
            <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
        </button>
    );
}
