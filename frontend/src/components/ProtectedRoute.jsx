"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { AuthLoadingSkeleton } from "@/components/PageSkeletons";

export function ProtectedRoute({ children }) {
    const { user, isLoading } = useAuth();
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        if (!isLoading && !user) {
            const next = encodeURIComponent(pathname || "/dashboard");
            router.replace(`/login?next=${next}`);
        }
    }, [isLoading, user, router, pathname]);

    if (isLoading) {
        return <AuthLoadingSkeleton />;
    }

    if (!user) return null;

    return children;
}

export function GuestRoute({ children }) {
    const { user, isLoading } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!isLoading && user) router.replace("/dashboard");
    }, [isLoading, user, router]);

    // Keep children visible while auth resolves so marketing/SEO HTML is not blank.
    if (!isLoading && user) return null;
    return children;
}
