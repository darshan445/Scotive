"use client";
import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

export function useXeroCallbackToast(onResolved) {
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        const result = searchParams.get("xero");
        if (!result) return;

        switch (result) {
            case "connected":
                break;
            case "cancelled":
            case "access_denied":
                toast("Xero connection cancelled", {
                    description: "No worries — connect anytime from Settings.",
                });
                break;
            case "wrong_scopes":
                toast.error("Xero scopes are wrong", {
                    description: "Xero rejected a scope we sent. Connect again — we only request offline_access plus invoices, contacts, and settings.",
                });
                break;
            case "state_invalid":
                toast.error("Session expired", {
                    description: "Please click Connect Xero again.",
                });
                break;
            case "error":
                toast.error("Something went wrong", {
                    description: "Please try connecting Xero again in a moment.",
                });
                break;
            default:
                toast.error("Xero connection failed", {
                    description: result.replace(/_/g, " "),
                });
                break;
        }
        const params = new URLSearchParams(searchParams.toString());
        params.delete("xero");
        const qs = params.toString();
        router.replace(qs ? `${pathname}?${qs}` : pathname);
        onResolved?.(result);
    }, [searchParams, router, pathname, onResolved]);
}
