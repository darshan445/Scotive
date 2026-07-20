"use client";

import { useRouter } from "next/navigation";
import { InvoiceDetailDrawer } from "@/components/InvoiceDetailDrawer";
import { notifyWorkspaceRefresh } from "@/lib/workspaceRefresh";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export function InvoiceDrawerClient({ invoiceId, fallbackHref = "/dashboard" }) {
    const router = useRouter();

    return (
        <ProtectedRoute>
            <InvoiceDetailDrawer
                invoiceId={invoiceId}
                open
                onClose={() => {
                    if (typeof window !== "undefined" && window.history.length > 1) {
                        router.back();
                    } else {
                        router.replace(fallbackHref);
                    }
                }}
                onChanged={() => notifyWorkspaceRefresh()}
            />
        </ProtectedRoute>
    );
}
