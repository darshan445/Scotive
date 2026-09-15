import Link from "next/link";
import { LegalSection, LegalShell } from "@/components/LegalShell";

const UPDATED = "September 14, 2026";
const CONTACT = "support@scotive.com";

export default function TermsPage() {
    return (
        <LegalShell title="Terms of Service" updated={UPDATED} testId="terms-page">
            <LegalSection id="agreement" title="1. Agreement to these Terms">
                <p>
                    These Terms of Service (“Terms”) govern your access to and use of Scotive
                    (the “Service”), including our website at scotive.com and related APIs.
                    By creating an account, connecting Gmail, connecting QuickBooks Online, or
                    otherwise using the Service, you agree to these Terms and to our{" "}
                    <Link href="/privacy">Privacy Policy</Link>.
                </p>
                <p>
                    If you use Scotive on behalf of a company or other entity, you represent that
                    you have authority to bind that entity, and “you” includes that entity.
                </p>
            </LegalSection>

            <LegalSection id="service" title="2. What Scotive does">
                <p>
                    Not a new books app. You keep QBO/Xero. We run the chase. You already
                    invoiced them. Scotive watches the thread and the open invoice, and handles
                    the next chase. Agency / studio ops or founder, ~8–40 people, B2B retainers,
                    Gmail or Outlook + QBO. Consultant / fractional with 8+ open invoices.
                    Depending on features you enable, the Service may:
                </p>
                <ul>
                    <li>Connect to your Google account with Gmail read and send permissions</li>
                    <li>Scan sent mail (and related threads) to detect invoices you sent</li>
                    <li>
                        Optionally connect to Intuit QuickBooks Online to import open invoices
                        and sync paid / not-paid status
                    </li>
                    <li>
                        When you mark a QuickBooks-linked invoice paid in Scotive, update that
                        invoice in QuickBooks (for example by creating a linked Payment)
                    </li>
                    <li>
                        Store a ledger of invoice facts (amounts, clients, due dates, status)
                        and evidence references — not a full copy of your mailbox or QuickBooks
                        company
                    </li>
                    <li>Read client replies for signals such as payment promises, disputes, and claims</li>
                    <li>
                        Draft follow-up and reply emails for your review using automated systems,
                        including third-party AI models
                    </li>
                    <li>
                        Send approved Friendly cadence from your connected Gmail or Outlook when you
                        have approved the rules; Firm/Final only when you click
                    </li>
                    <li>Optionally email you a daily digest of items that need attention</li>
                </ul>
                <p>
                    Approved Friendly cadence = the user approves the rules once (or per client),
                    not every Friendly email. Firm / Final still need a click. You remain
                    responsible for reviewing Firm/Final and the content of emails sent from your
                    address. Gmail / Outlook is the actual conversation. You keep QBO/Xero as the
                    ledger. Scotive does not replace QuickBooks as your accounting system of record.
                    Scotive is not a payments company. Not collections.
                </p>
            </LegalSection>

            <LegalSection id="eligibility" title="3. Eligibility and accounts">
                <p>
                    You must be at least 18 years old (or the age of majority where you live) and
                    able to form a binding contract. You must provide accurate registration
                    information and keep your password confidential. You are responsible for
                    activity under your account.
                </p>
                <p>
                    One person or organization should not create multiple accounts to evade
                    limits, bans, or these Terms.
                </p>
            </LegalSection>

            <LegalSection id="gmail" title="4. Email connection (Gmail or Outlook)">
                <p>
                    To use core features you must connect a Gmail or Outlook / Microsoft 365
                    mailbox. Sign-in is completed through <strong>Unipile</strong>, our email
                    connection partner — Google or Microsoft may show Unipile on the consent
                    screen. Through that connection Scotive uses:
                </p>
                <ul>
                    <li>
                        <strong>Mail read</strong> — to detect invoices you sent, read
                        related thread context, and keep your ledger current
                    </li>
                    <li>
                        <strong>Mail send</strong> — to send approved Friendly cadence, Firm/Final you click,
                        and optional digests from your address
                    </li>
                    <li>
                        <strong>Mailbox identity</strong> — to identify the connected address and
                        display name used when signing drafts
                    </li>
                </ul>
                <p>
                    Your use of email through Scotive is also subject to Google’s or Microsoft’s
                    and Unipile’s terms and policies. You can disconnect anytime in Settings.
                    Disconnecting removes the stored mailbox link; your Scotive ledger may remain
                    until you delete your account.
                </p>
                <p>
                    You represent that you have the right to connect the mailbox you authorize and
                    that your use complies with applicable law and your clients’ expectations.
                </p>
            </LegalSection>

            <LegalSection id="qbo" title="5. QuickBooks Online connection (optional)">
                <p>
                    You may optionally connect Intuit QuickBooks Online. When you do, Scotive
                    requests accounting API access to:
                </p>
                <ul>
                    <li>
                        Read open (unpaid) invoices and related customer fields needed to build
                        and update your ledger
                    </li>
                    <li>
                        Read paid / not-paid status (for example Balance and related payment
                        signals) so we can mark invoices Paid in Scotive when QuickBooks reports
                        them paid
                    </li>
                    <li>
                        Create or update Payment records linked to an invoice when{" "}
                        <strong>you</strong> mark that invoice paid or confirm payment received
                        in Scotive
                    </li>
                </ul>
                <p>
                    Your use of QuickBooks through Scotive is also subject to Intuit’s terms and
                    policies. Intuit is not a party to these Terms and is not responsible for the
                    Service. You can disconnect QuickBooks at any time in Settings. Disconnecting
                    removes stored OAuth tokens; your Scotive ledger may remain until you delete
                    your account.
                </p>
                <p>
                    You represent that you have authority to connect the QuickBooks company you
                    authorize, and that syncing paid status (including writing Payments back to
                    QuickBooks) is permitted for that company. Scotive does not replace QuickBooks
                    as your accounting system of record.
                </p>
            </LegalSection>

            <LegalSection id="ai" title="6. AI-assisted features">
                <p>
                    Scotive uses machine learning and third-party AI providers to extract invoice
                    details from email content and to draft follow-up messages. Outputs can be
                    incomplete, incorrect, or inappropriate. You must review all drafts, ledger
                    fields, and review-queue items before relying on them or sending email.
                </p>
                <p>
                    Scotive’s product policy is that your email content is processed to operate
                    the Service and is <strong>not used by Scotive to train its own models</strong>.
                    Processing by third-party AI providers is described in our Privacy Policy.
                </p>
            </LegalSection>

            <LegalSection id="your-responsibilities" title="7. Your responsibilities">
                <p>You agree that you will not:</p>
                <ul>
                    <li>Use the Service for unlawful, harassing, deceptive, or abusive communications</li>
                    <li>Misrepresent your identity or your authority to collect payment</li>
                    <li>Attempt to access another user’s account or data without authorization</li>
                    <li>Reverse engineer, scrape, or overload the Service except as allowed by law</li>
                    <li>Use Scotive to send spam or content that violates Google’s or email anti-abuse rules</li>
                    <li>Upload or process content you do not have rights to process</li>
                </ul>
                <p>
                    You are solely responsible for the content of emails you send, for tax and
                    accounting treatment of invoices (including records in QuickBooks), and for
                    disputes with your clients. Scotive is a software tool, not your attorney,
                    accountant, or collection agency.
                </p>
            </LegalSection>

            <LegalSection id="ip" title="8. Intellectual property">
                <p>
                    Scotive and its branding, software, and documentation are owned by Scotive or
                    its licensors. Subject to these Terms, we grant you a limited, non-exclusive,
                    non-transferable license to use the Service for your internal business purposes.
                </p>
                <p>
                    You retain rights in your account data, email content, and QuickBooks company
                    data. You grant Scotive a worldwide license to host, process, and transmit that
                    content solely as needed to provide and improve the Service (including security,
                    support, and reliability), consistent with the Privacy Policy.
                </p>
            </LegalSection>

            <LegalSection id="availability" title="9. Availability and changes">
                <p>
                    We aim for reliable uptime but do not guarantee uninterrupted or error-free
                    operation. Features may change as we improve the product. We may suspend or
                    terminate access for abuse, security risk, non-payment (if applicable), or
                    material breach of these Terms.
                </p>
                <p>
                    We may update these Terms from time to time. Material changes will be posted
                    on this page with an updated date. Continued use after changes become
                    effective constitutes acceptance, except where applicable law requires
                    additional consent.
                </p>
            </LegalSection>

            <LegalSection id="disclaimer" title="10. Disclaimers">
                <p>
                    THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE.” TO THE MAXIMUM EXTENT
                    PERMITTED BY LAW, SCOTIVE DISCLAIMS ALL WARRANTIES, WHETHER EXPRESS, IMPLIED,
                    OR STATUTORY, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE,
                    AND NON-INFRINGEMENT. WE DO NOT WARRANT THAT LEDGER DATA, QUICKBOOKS SYNC,
                    AI EXTRACTIONS, OR DRAFTS WILL BE ACCURATE OR COMPLETE.
                </p>
            </LegalSection>

            <LegalSection id="liability" title="11. Limitation of liability">
                <p>
                    TO THE MAXIMUM EXTENT PERMITTED BY LAW, SCOTIVE AND ITS SUPPLIERS WILL NOT BE
                    LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES,
                    OR FOR LOST PROFITS, REVENUE, DATA, OR GOODWILL, ARISING FROM YOUR USE OF THE
                    SERVICE. OUR TOTAL LIABILITY FOR ANY CLAIM RELATING TO THE SERVICE WILL NOT
                    EXCEED THE GREATER OF (A) AMOUNTS YOU PAID US FOR THE SERVICE IN THE TWELVE
                    MONTHS BEFORE THE CLAIM OR (B) USD $100, IF YOU HAVE NOT PAID US.
                </p>
                <p>
                    Some jurisdictions do not allow certain limitations; in those cases, the
                    above limits apply to the fullest extent permitted.
                </p>
            </LegalSection>

            <LegalSection id="indemnity" title="12. Indemnity">
                <p>
                    You will defend and indemnify Scotive against claims, damages, and expenses
                    (including reasonable attorneys’ fees) arising from your content, your emails,
                    your misuse of the Service, or your violation of these Terms or applicable law.
                </p>
            </LegalSection>

            <LegalSection id="law" title="13. Governing law">
                <p>
                    These Terms are governed by the laws of the State of Delaware, USA, excluding
                    conflict-of-law rules, unless mandatory consumer protections in your place of
                    residence provide otherwise. Courts in Delaware will have exclusive
                    jurisdiction, subject to those mandatory protections.
                </p>
            </LegalSection>

            <LegalSection id="misc" title="14. Miscellaneous">
                <p>
                    These Terms are the entire agreement between you and Scotive regarding the
                    Service. If a provision is unenforceable, the remainder stays in effect.
                    Failure to enforce a provision is not a waiver. You may not assign these Terms
                    without our consent; we may assign them in connection with a merger, acquisition,
                    or sale of assets.
                </p>
            </LegalSection>

            <LegalSection id="contact" title="15. Contact">
                <p>
                    Questions about these Terms:{" "}
                    <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
                </p>
                <p>
                    Privacy questions: see our{" "}
                    <Link href="/privacy">Privacy Policy</Link> or email{" "}
                    <a href="mailto:privacy@scotive.com">privacy@scotive.com</a>.
                </p>
            </LegalSection>
        </LegalShell>
    );
}
