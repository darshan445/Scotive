"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ChevronDown, Menu, X } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { RESOURCE_LINKS } from "@/lib/guides";
import {
    ACCOUNTING_INTEGRATIONS,
    EMAIL_INTEGRATIONS,
    TRIAL_CTA,
} from "@/lib/site";
import { cn } from "@/lib/utils";

const INTEGRATION_CATEGORIES = [
    { id: "accounting", label: "Accounting", items: ACCOUNTING_INTEGRATIONS },
    { id: "email", label: "Email", items: EMAIL_INTEGRATIONS },
];

const RESOURCES = RESOURCE_LINKS.map((item) => ({
    href: item.path,
    label: item.navLabel,
}));

function NavLink({ href, active, onClick, children }) {
    return (
        <Link
            href={href}
            onClick={onClick}
            className={`px-3 py-2 rounded-md transition-colors ${
                active ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
            }`}
        >
            {children}
        </Link>
    );
}

function IntegrationLogoTile({ item, onNavigate }) {
    return (
        <Link
            href={item.href}
            onClick={onNavigate}
            className="integration-logo-tile group"
            aria-label={item.name}
        >
            <img src={item.logo} alt="" className="h-8 w-auto max-h-8 max-w-[72%] object-contain pointer-events-none" />
        </Link>
    );
}

export function MarketingHeader({ activePath = "", loginTestId, signupTestId }) {
    const [mobileOpen, setMobileOpen] = useState(false);
    const [integrationsOpen, setIntegrationsOpen] = useState(false);
    const [resourcesOpen, setResourcesOpen] = useState(false);
    const [category, setCategory] = useState("accounting");
    const integrationsTimer = useRef(null);
    const resourcesTimer = useRef(null);
    const integrationsPinned = useRef(false);
    const resourcesPinned = useRef(false);

    const activeCategory = INTEGRATION_CATEGORIES.find((c) => c.id === category) || INTEGRATION_CATEGORIES[0];
    const resourcesActive =
        activePath === "/guides" || RESOURCE_LINKS.some((item) => item.path === activePath);

    function openPanel(which) {
        if (which === "integrations") {
            if (integrationsTimer.current) clearTimeout(integrationsTimer.current);
            resourcesPinned.current = false;
            setResourcesOpen(false);
            setIntegrationsOpen(true);
        } else {
            if (resourcesTimer.current) clearTimeout(resourcesTimer.current);
            integrationsPinned.current = false;
            setIntegrationsOpen(false);
            setResourcesOpen(true);
        }
    }

    function scheduleClose(which) {
        if (which === "integrations" && integrationsPinned.current) return;
        if (which === "resources" && resourcesPinned.current) return;
        const setter = which === "integrations" ? setIntegrationsOpen : setResourcesOpen;
        const timer = which === "integrations" ? integrationsTimer : resourcesTimer;
        timer.current = setTimeout(() => setter(false), 160);
    }

    function closeMenus() {
        integrationsPinned.current = false;
        resourcesPinned.current = false;
        setIntegrationsOpen(false);
        setResourcesOpen(false);
    }

    function togglePanel(which) {
        if (which === "integrations") {
            const next = !(integrationsOpen && integrationsPinned.current);
            integrationsPinned.current = next;
            resourcesPinned.current = false;
            setResourcesOpen(false);
            setIntegrationsOpen(next);
        } else {
            const next = !(resourcesOpen && resourcesPinned.current);
            resourcesPinned.current = next;
            integrationsPinned.current = false;
            setIntegrationsOpen(false);
            setResourcesOpen(next);
        }
    }

    return (
        <header className="border-b border-border/70 bg-background/90 backdrop-blur-sm sticky top-0 z-40">
            <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="h-[4.25rem] flex items-center gap-3">
                    <BrandMark size="md" />

                    <nav className="hidden md:flex flex-1 items-center justify-center gap-0.5 text-sm whitespace-nowrap" aria-label="Primary">
                        <div
                            onMouseEnter={() => openPanel("integrations")}
                            onMouseLeave={() => scheduleClose("integrations")}
                        >
                            <Link
                                href="/integrations"
                                className={`inline-flex items-center gap-1 px-3 py-2 rounded-md transition-colors ${
                                    activePath === "/integrations" || integrationsOpen
                                        ? "text-foreground font-medium"
                                        : "text-muted-foreground hover:text-foreground"
                                }`}
                                aria-expanded={integrationsOpen}
                                aria-haspopup="true"
                                onClick={closeMenus}
                            >
                                Integrations
                                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${integrationsOpen ? "rotate-180" : ""}`} />
                            </Link>
                        </div>

                        <NavLink href="/#how-it-works" active={false} onClick={closeMenus}>
                            How it works
                        </NavLink>
                        <NavLink href="/pricing" active={activePath === "/pricing"} onClick={closeMenus}>
                            Pricing
                        </NavLink>

                        <div
                            className="relative"
                            onMouseEnter={() => openPanel("resources")}
                            onMouseLeave={() => scheduleClose("resources")}
                        >
                            <button
                                type="button"
                                className={`inline-flex items-center gap-1 px-3 py-2 rounded-md transition-colors ${
                                    resourcesActive || resourcesOpen
                                        ? "text-foreground font-medium"
                                        : "text-muted-foreground hover:text-foreground"
                                }`}
                                aria-expanded={resourcesOpen}
                                aria-haspopup="true"
                                onClick={() => togglePanel("resources")}
                            >
                                Resources
                                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${resourcesOpen ? "rotate-180" : ""}`} />
                            </button>
                            {resourcesOpen ? (
                                <div className="absolute left-0 top-full pt-3 z-50">
                                    <div className="w-72 rounded-xl border border-border bg-card shadow-xl py-2">
                                        {RESOURCES.map((item) => (
                                            <Link
                                                key={item.href}
                                                href={item.href}
                                                className="block px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                                                onClick={() => {
                                                    resourcesPinned.current = false;
                                                    setResourcesOpen(false);
                                                }}
                                            >
                                                {item.label}
                                            </Link>
                                        ))}
                                    </div>
                                </div>
                            ) : null}
                        </div>
                    </nav>

                    <div className="flex items-center gap-2 shrink-0 ml-auto">
                        <Link
                            href="/login"
                            className="text-sm font-medium px-2 py-2 text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
                            data-testid={loginTestId}
                        >
                            Log in
                        </Link>
                        <Link
                            href="/register"
                            className={cn(
                                "hidden sm:inline-flex btn-pill-outline text-sm whitespace-nowrap",
                                "hover:bg-primary hover:text-primary-foreground hover:border-primary",
                            )}
                            data-testid={signupTestId}
                        >
                            {TRIAL_CTA}
                        </Link>
                        <button
                            type="button"
                            className="md:hidden inline-flex items-center justify-center w-10 h-10 rounded-md text-foreground hover:bg-muted"
                            aria-label={mobileOpen ? "Close menu" : "Open menu"}
                            aria-expanded={mobileOpen}
                            onClick={() => setMobileOpen((v) => !v)}
                        >
                            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                        </button>
                    </div>
                </div>

                {integrationsOpen ? (
                    <div
                        className="hidden md:block absolute left-4 right-4 sm:left-6 sm:right-6 lg:left-8 lg:right-8 top-full z-50 pt-2"
                        onMouseEnter={() => openPanel("integrations")}
                        onMouseLeave={() => scheduleClose("integrations")}
                    >
                        <div className="rounded-2xl border border-border bg-card shadow-xl p-3 flex gap-2">
                            <div className="w-48 shrink-0 p-1.5 flex flex-col gap-0.5">
                                {INTEGRATION_CATEGORIES.map((cat) => (
                                    <button
                                        key={cat.id}
                                        type="button"
                                        onMouseEnter={() => setCategory(cat.id)}
                                        onFocus={() => setCategory(cat.id)}
                                        onClick={() => setCategory(cat.id)}
                                        aria-current={category === cat.id ? "true" : undefined}
                                        className={`w-full text-left rounded-lg px-3 py-2.5 text-sm transition-colors ${
                                            category === cat.id
                                                ? "bg-muted text-foreground font-medium"
                                                : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                                        }`}
                                    >
                                        {cat.label}
                                    </button>
                                ))}
                            </div>
                            <div className="flex-1 rounded-xl bg-muted/40 p-3">
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                                    {activeCategory.items.map((item) => (
                                        <IntegrationLogoTile
                                            key={item.name}
                                            item={item}
                                            onNavigate={() => {
                                                integrationsPinned.current = false;
                                                setIntegrationsOpen(false);
                                            }}
                                        />
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                ) : null}
            </div>

            {mobileOpen ? (
                <div className="md:hidden border-t border-border bg-background px-4 py-3 space-y-1">
                    <Link
                        href="/integrations"
                        className="block px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                        onClick={() => setMobileOpen(false)}
                    >
                        Integrations
                    </Link>
                    <Link
                        href="/#how-it-works"
                        className="block px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                        onClick={() => setMobileOpen(false)}
                    >
                        How it works
                    </Link>
                    <Link
                        href="/pricing"
                        className="block px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                        onClick={() => setMobileOpen(false)}
                    >
                        Pricing
                    </Link>
                    <p className="px-3 pt-3 pb-1 eyebrow">
                        Resources
                    </p>
                    {RESOURCES.map((item) => (
                        <Link
                            key={item.href}
                            href={item.href}
                            className="block px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                            onClick={() => setMobileOpen(false)}
                        >
                            {item.label}
                        </Link>
                    ))}
                    <Link
                        href="/contact"
                        className="block px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                        onClick={() => setMobileOpen(false)}
                    >
                        Contact
                    </Link>
                    <Link
                        href="/register"
                        className={cn(
                            "block mt-2 text-center btn-pill-outline text-sm py-2.5",
                            "hover:bg-primary hover:text-primary-foreground hover:border-primary",
                        )}
                        onClick={() => setMobileOpen(false)}
                    >
                        {TRIAL_CTA}
                    </Link>
                </div>
            ) : null}
        </header>
    );
}
