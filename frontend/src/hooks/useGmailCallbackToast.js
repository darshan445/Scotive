"use client";
import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

/**
 * Consumes ?mail= / ?gmail= / ?outlook= after Unipile redirect and clears them from URL.
 */
export function useGmailCallbackToast(onResolved) {
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        const result =
            searchParams.get("mail") ||
            searchParams.get("gmail") ||
            searchParams.get("outlook");
        if (!result) return;

        const providerParam = (searchParams.get("provider") || "").toLowerCase();
        const providerLabel =
            providerParam === "outlook" || searchParams.has("outlook")
                ? "Outlook"
                : "Gmail";

        switch (result) {
            case "connected":
                toast.success(`${providerLabel} connected`, {
                    description: "Mailbox linked. Building your ledger next.",
                });
                break;
            case "send_missing":
                toast.warning("Connected — sending disabled", {
                    description:
                        "Reconnect and grant send permission to enable one-tap chasers.",
                });
                break;
            case "read_missing":
                toast.error("Read access is required", {
                    description: "Scotive can't build a ledger without reading your mail. Try again.",
                });
                break;
            case "cancelled":
            case "access_denied":
                toast(`${providerLabel} connection cancelled`, {
                    description: "No worries — try again whenever you're ready.",
                });
                break;
            case "state_invalid":
                toast.error("Session expired", {
                    description: `Please click Connect ${providerLabel} again.`,
                });
                break;
            case "error":
                toast.error("Something went wrong", {
                    description: "Please try connecting again in a moment.",
                });
                break;
            default:
                break;
        }
        const params = new URLSearchParams(searchParams.toString());
        params.delete("mail");
        params.delete("gmail");
        params.delete("outlook");
        params.delete("provider");
        const qs = params.toString();
        router.replace(qs ? `${pathname}?${qs}` : pathname);
        onResolved?.(result);
    }, [searchParams, router, pathname, onResolved]);
}
