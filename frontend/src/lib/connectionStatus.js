export function needsReconnect(status) {
    return status === "revoked" || status === "reauth_required";
}
