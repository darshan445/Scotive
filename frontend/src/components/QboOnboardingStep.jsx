"use client";
import { toast } from "sonner";
import { api } from "@/lib/api";

/**
 * After QBO OAuth: mark step + import unpaid invoices (fast).
 * Conversation match / status re-eval runs in the background — dashboard shows progress.
 */
export async function finishQboOnboardingImport() {
    await api.post("/onboarding/qbo-step", { action: "connected" });
    const { data } = await api.post("/qbo/import");
    return data?.counts || {};
}

export function toastQboImportComplete(counts = {}) {
    const n = Number(counts.fetched || 0)
        || ((counts.created || 0) + (counts.updated || 0) + (counts.merged || 0));
    if (n > 0) {
        toast.success("QuickBooks connected", {
            description: `Imported ${n} invoice${n === 1 ? "" : "s"}`,
        });
        return;
    }
    toast.success("QuickBooks connected");
}
