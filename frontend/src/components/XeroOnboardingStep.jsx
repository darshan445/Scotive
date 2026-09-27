"use client";
import { toast } from "sonner";
import { api, unwrapData, LONG_JOB_TIMEOUT_MS } from "@/lib/api";

export async function finishXeroOnboardingImport() {
    const { data } = await api.post("/v1/xero/import", null, { timeout: LONG_JOB_TIMEOUT_MS });
    return unwrapData(data)?.counts || {};
}

export function toastXeroImportComplete(counts = {}) {
    const n = Number(counts.fetched || 0)
        || ((counts.created || 0) + (counts.updated || 0) + (counts.merged || 0));
    if (n > 0) {
        toast.success("Xero connected", {
            description: `Imported ${n} invoice${n === 1 ? "" : "s"}`,
        });
        return;
    }
    toast.success("Xero connected");
}
