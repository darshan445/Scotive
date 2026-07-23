"use client";
import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

/**
 * Consumes ?qbo=<result> after the OAuth redirect and clears it from URL.
 * result values: connected | cancelled | access_denied | state_invalid | error
 */
export function useQboCallbackToast(onResolved) {
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        const result = searchParams.get("qbo");
        if (!result) return;

        switch (result) {
            case "connected":
                toast.success("QuickBooks connected", {
                    description: "Your sandbox company is linked. Invoice import comes next.",
                });
                break;
            case "cancelled":
            case "access_denied":
                toast("QuickBooks connection cancelled", {
                    description: "No worries — connect anytime from Settings.",
                });
                break;
            case "state_invalid":
                toast.error("Session expired", {
                    description: "Please click Connect QuickBooks again.",
                });
                break;
            case "error":
                toast.error("Something went wrong", {
                    description: "Please try connecting QuickBooks again in a moment.",
                });
                break;
            default:
                toast.error("QuickBooks connection failed", {
                    description: result.replace(/_/g, " "),
                });
                break;
        }
        const params = new URLSearchParams(searchParams.toString());
        params.delete("qbo");
        const qs = params.toString();
        router.replace(qs ? `${pathname}?${qs}` : pathname);
        onResolved?.(result);
    }, [searchParams, router, pathname, onResolved]);
}
