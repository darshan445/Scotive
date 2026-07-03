import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

/**
 * Consumes ?gmail=<result> after the OAuth redirect and clears it from URL.
 * result values: connected | send_missing | cancelled | read_missing | state_invalid | error
 */
export function useGmailCallbackToast(onResolved) {
    const [params, setParams] = useSearchParams();

    useEffect(() => {
        const result = params.get("gmail");
        if (!result) return;

        switch (result) {
            case "connected":
                toast.success("Gmail connected", {
                    description: "Read + send access granted. Building your ledger next.",
                });
                break;
            case "send_missing":
                toast.warning("Connected — sending disabled", {
                    description:
                        "You granted read access but skipped 'Send email'. Reconnect and check both boxes to enable one-tap chasers.",
                });
                break;
            case "read_missing":
                toast.error("Read access is required", {
                    description: "Scotive can't build a ledger without reading your Gmail. Try again and grant read access.",
                });
                break;
            case "cancelled":
            case "access_denied":
                toast("Gmail connection cancelled", {
                    description: "No worries — try again whenever you're ready.",
                });
                break;
            case "state_invalid":
                toast.error("Session expired", {
                    description: "Please click Connect Gmail again.",
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
        params.delete("gmail");
        setParams(params, { replace: true });
        onResolved?.(result);
    }, [params, setParams, onResolved]);
}
