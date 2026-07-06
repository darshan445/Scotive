import { useEffect, useRef, useSyncExternalStore } from "react";

/** Bump to invalidate all workspace views that share invoice/sync state. */
let version = 0;
const listeners = new Set();

function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function getSnapshot() {
    return version;
}

/** Notify every subscribed view to refetch (Today digest, chase queue, ledger hooks, etc.). */
export function notifyWorkspaceRefresh() {
    version += 1;
    listeners.forEach((listener) => listener());
}

export function useWorkspaceVersion() {
    return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/**
 * Run `fn` whenever workspace data changes (skip the initial mount — components fetch on load).
 */
export function useWorkspaceRefreshEffect(fn) {
    const v = useWorkspaceVersion();
    const fnRef = useRef(fn);
    fnRef.current = fn;
    const mounted = useRef(false);

    useEffect(() => {
        if (!mounted.current) {
            mounted.current = true;
            return;
        }
        fnRef.current();
    }, [v]);
}
