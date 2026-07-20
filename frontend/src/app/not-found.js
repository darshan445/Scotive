"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function NotFound() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/");
    }, [router]);

    return (
        <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground text-sm">
            Page not found — redirecting…
        </div>
    );
}
