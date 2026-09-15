import Link from "next/link";
import { BrandMark } from "@/components/BrandMark";
import { PRICE_FOOTER, TRIAL_LABEL } from "@/lib/site";

export function MarketingFooter() {
    return (
        <footer className="border-t border-border mt-auto bg-background">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid gap-10 md:grid-cols-4">
                <div>
                    <BrandMark />
                    <p className="type-body mt-3 text-sm max-w-sm">
                        Get paid without the awkward follow-up. The next email is in their words. {TRIAL_LABEL}.
                    </p>
                </div>
                <div>
                    <div className="type-title text-sm mb-3">Product</div>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                        <li><Link href="/" className="hover:text-foreground">Home</Link></li>
                        <li><Link href="/integrations" className="hover:text-foreground">Integrations</Link></li>
                        <li><Link href="/pricing" className="hover:text-foreground">Pricing</Link></li>
                        <li><Link href="/register" className="hover:text-foreground">Start free trial</Link></li>
                    </ul>
                </div>
                <div>
                    <div className="type-title text-sm mb-3">Resources</div>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                        <li><Link href="/guides" className="hover:text-foreground">Resources</Link></li>
                        <li><Link href="/invoice-reminder-software" className="hover:text-foreground">Invoice reminder software</Link></li>
                        <li><Link href="/past-due-invoice-reminder" className="hover:text-foreground">Past due invoice reminder</Link></li>
                        <li><Link href="/payment-reminder-email-template" className="hover:text-foreground">Payment reminder email</Link></li>
                        <li><Link href="/how-to-chase-outstanding-invoices" className="hover:text-foreground">How to chase invoices</Link></li>
                        <li><Link href="/quickbooks-invoice-reminders" className="hover:text-foreground">QuickBooks reminders</Link></li>
                        <li><Link href="/xero-invoice-reminders" className="hover:text-foreground">Xero reminders</Link></li>
                        <li><Link href="/freshbooks-invoice-reminders" className="hover:text-foreground">FreshBooks reminders</Link></li>
                    </ul>
                </div>
                <div>
                    <div className="type-title text-sm mb-3">Company</div>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                        <li><Link href="/contact" className="hover:text-foreground">Contact</Link></li>
                        <li><Link href="/terms" className="hover:text-foreground">Terms of Service</Link></li>
                        <li><Link href="/privacy" className="hover:text-foreground">Privacy Policy</Link></li>
                        <li>
                            <a href="mailto:contact@scotive.com" className="hover:text-foreground">
                                contact@scotive.com
                            </a>
                        </li>
                    </ul>
                </div>
            </div>
            <div className="border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 flex flex-wrap justify-between items-center gap-3 text-xs text-muted-foreground">
                    <span>© {new Date().getFullYear()} Scotive. All rights reserved.</span>
                    <span>{PRICE_FOOTER}</span>
                </div>
            </div>
        </footer>
    );
}
