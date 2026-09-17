import Link from "next/link";
import { LegalSection, LegalShell } from "@/components/LegalShell";

const UPDATED = "September 14, 2026";
const PRIVACY_EMAIL = "privacy@scotive.com";
const SUPPORT_EMAIL = "support@scotive.com";

export default function PrivacyPage() {
    return (
        <LegalShell title="Privacy Policy" updated={UPDATED} testId="privacy-page">
            <LegalSection id="intro" title="1. Introduction">
                <p>
                    This Privacy Policy explains how Scotive (“we”, “us”) collects, uses, and
                    shares information when you use scotive.com and the Scotive service
                    (the “Service”). Not a new books app. You keep QBO/Xero. We run the chase.
                    You already invoiced them. Scotive watches the thread and the open invoice, and
                    handles the next chase.                     Live connections today: Gmail, Outlook, and QuickBooks Online
                    (required — invoices come from your invoicing tool). Approved Friendly cadence can send on the clock. Firm/Final
                    still need a click. Pay link in the draft. AI-assisted extraction and drafting.
                </p>
                <p>
                    By using the Service you acknowledge this Policy. Related terms are in our{" "}
                    <Link href="/terms">Terms of Service</Link>.
                </p>
            </LegalSection>

            <LegalSection id="controller" title="2. Who we are">
                <p>
                    The Service is operated under the brand <strong>Scotive</strong>
                    (websites at scotive.com / www.scotive.com; API at api.scotive.com).
                </p>
                <p>
                    Privacy requests: <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>
                    <br />
                    General support: <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
                </p>
            </LegalSection>

            <LegalSection id="collect" title="3. Information we collect">
                <p>
                    <strong>Account information.</strong> Email address, password (stored as a
                    one-way hash), optional display name, and preferences such as timezone and
                    digest settings.
                </p>
                <p>
                    <strong>Email mailbox (Gmail or Outlook).</strong> When you connect email, the
                    sign-in screen may show <strong>Unipile</strong>, our email connection partner.
                    Unipile handles secure Google or Microsoft authorization. After you connect, we
                    receive a mailbox link (account identifier), the connected email address, and
                    connection status needed to read invoice-related mail and send follow-ups you
                    approve. You can disconnect anytime in Settings.
                </p>
                <p>
                    <strong>Intuit / QuickBooks Online connection.</strong> When you
                    connect QuickBooks Online we receive OAuth tokens, your QuickBooks company
                    (realm) identifier, granted scopes (accounting API access), and connection
                    status. Access and refresh tokens are encrypted at rest before storage. We
                    may also receive company display metadata Intuit returns with the connection.
                </p>
                <p>
                    <strong>Invoice and payment-ops data we derive or import.</strong> We store a
                    structured ledger and related records, which may include:
                </p>
                <ul>
                    <li>
                        Client name and email, invoice references, amounts, currency, and dates —
                        imported from QuickBooks invoice and customer records you authorize us to
                        read, then matched to Gmail or Outlook threads
                    </li>
                    <li>
                        QuickBooks identifiers (for example invoice Id, DocNumber, Balance) and
                        paid / not-paid status we sync from QuickBooks
                    </li>
                    <li>Status (for example invoiced, overdue, promised, disputed, paid)</li>
                    <li>
                        Evidence snippets and quotes (for example a promise date or dispute phrase)
                        and Gmail message/thread identifiers needed to reopen context
                    </li>
                    <li>Review-queue items when extraction confidence is low</li>
                    <li>Chase drafts you generate or that the escalation ladder prepares for review</li>
                    <li>Records of chase emails you chose to send (subject, body, timestamps)</li>
                    <li>Optional suppressed-sender list and client-merge preferences</li>
                </ul>
                <p>
                    <strong>We do not store your entire mailbox or your entire QuickBooks company.</strong>{" "}
                    We store extracted or imported facts needed for the ledger and drafts, evidence
                    needed for tracking, and references so we can fetch conversation context from
                    Gmail when you open an invoice and keep open / paid status in sync with
                    QuickBooks when connected.
                </p>
                <p>
                    <strong>Usage and security data.</strong> We may process technical logs
                    (for example IP address, timestamps, error diagnostics) and login-attempt
                    records used for rate limiting and account security.
                </p>
            </LegalSection>

            <LegalSection id="use" title="4. How we use information">
                <p>We use information to:</p>
                <ul>
                    <li>Provide, maintain, and secure the Service</li>
                    <li>
                        Detect invoices you sent via Gmail or Outlook and, when connected, import open invoices
                        from QuickBooks into your ledger
                    </li>
                    <li>
                        Keep your open / paid ledger current, including syncing paid status from
                        QuickBooks and matching Gmail/Outlook conversations to QuickBooks-sourced invoices
                    </li>
                    <li>Interpret client replies (promises, disputes, payment claims, questions)</li>
                    <li>Generate follow-up and reply drafts for your review</li>
                    <li>
                        Send approved Friendly cadence from your connected Gmail or Outlook when you
                        have approved the rules; Firm/Final only when you click; optional daily
                        digest you enabled
                    </li>
                    <li>
                        When you mark an invoice paid or confirm payment received in Scotive for a
                        QuickBooks-linked invoice, update that invoice in QuickBooks (for example by
                        creating a linked Payment) so Balance reflects what you confirmed
                    </li>
                    <li>Operate settings such as escalation timing and digests</li>
                    <li>Respond to support requests and enforce our Terms</li>
                    <li>
                        Improve reliability and product quality using aggregated or de-identified
                        insights where feasible
                    </li>
                </ul>
            </LegalSection>

            <LegalSection id="ai" title="5. Artificial intelligence processing">
                <p>
                    To extract invoice details and draft emails, relevant content (for example
                    message subjects, body excerpts, PDF text snippets, and ledger fields) may be
                    sent to third-party AI infrastructure — currently{" "}
                    <strong>OpenAI</strong> (Chat Completions API, gpt-4o-mini). That processing is
                    for <strong>inference</strong> to operate features you use.
                </p>
                <p>
                    <strong>Scotive’s policy:</strong> we do not use your email content to train
                    Scotive’s own models. We configure and select providers with the intent that
                    customer content is not used to train their foundation models where the
                    provider offers such terms; provider policies may change, and you should
                    review OpenAI’s privacy terms as well.
                </p>
                <p>
                    AI outputs can be wrong. Always review drafts and ledger fields before acting.
                </p>
            </LegalSection>

            <LegalSection id="sharing" title="6. Who we share information with">
                <p>We share information only as needed to run the Service:</p>
                <ul>
                    <li>
                        <strong>Unipile</strong> — our email connection partner. Google or
                        Microsoft authorization for Gmail / Outlook runs through Unipile; they
                        provide the API we use to read mailbox data and send messages you approve.
                        Your use is also subject to Unipile’s, Google’s, and Microsoft’s terms and
                        policies
                    </li>
                    <li>
                        <strong>Google / Microsoft</strong> — account sign-in and mailbox access as
                        authorized through Unipile (read mail, send approved messages)
                    </li>
                    <li>
                        <strong>Intuit / QuickBooks Online</strong> — OAuth and QuickBooks Online
                        Accounting API (read open invoices and related customer fields you
                        authorize; write payment updates when you mark a linked invoice paid in
                        Scotive). Your use of QuickBooks remains subject to Intuit’s terms and
                        privacy policy
                    </li>
                    <li>
                        <strong>OpenAI</strong> — AI extraction and drafting as described above
                    </li>
                    <li>
                        <strong>Hosting and infrastructure</strong> — for example our application
                        hosting and database providers that process data on our behalf under
                        contractual obligations
                    </li>
                    <li>
                        <strong>Professional advisors or authorities</strong> when required by law
                        or to protect rights, safety, and security
                    </li>
                    <li>
                        <strong>Successors</strong> in a merger, acquisition, or asset sale, subject
                        to continued protection consistent with this Policy
                    </li>
                </ul>
                <p>
                    We do not sell your personal information. Chase emails and digests are sent
                    from <strong>your</strong> connected Gmail or Outlook account to recipients you
                    choose (or to you, for digests). QuickBooks data stays in your Intuit company except for the
                    ledger facts and tokens we store to operate the integration.
                </p>
            </LegalSection>

            <LegalSection id="retention" title="7. Retention">
                <p>
                    We retain account and ledger data while your account is active. OAuth tokens
                    are kept only while the related connection remains active (Gmail and/or
                    QuickBooks), or until they expire or are revoked. Security logs are kept for
                    a limited period needed for abuse prevention.
                </p>
                <p>
                    When you delete your account (Settings → delete account, with email
                    confirmation), we delete your user record and associated Service data such as
                    invoices, events, receipts, review items, chase drafts and sends, Gmail and
                    QuickBooks connection and sync state, settings, merge prompts, and related
                    tokens — subject to short-lived backups and legal retention requirements.
                </p>
                <p>
                    Disconnecting Gmail or QuickBooks removes stored tokens for that connection
                    but does not by itself erase your ledger; delete your account if you want a
                    full wipe.
                </p>
            </LegalSection>

            <LegalSection id="security" title="8. Security">
                <p>
                    We use industry-standard measures appropriate to the sensitivity of the data,
                    including encrypted transport (HTTPS), hashed passwords, and encryption of
                    Gmail and QuickBooks OAuth tokens at rest. No method of transmission or
                    storage is 100% secure; we cannot guarantee absolute security.
                </p>
            </LegalSection>

            <LegalSection id="rights" title="9. Your choices and rights">
                <p>Depending on where you live, you may have rights to:</p>
                <ul>
                    <li>Access or export personal data we hold about you</li>
                    <li>Correct inaccurate account information</li>
                    <li>Delete your account and associated Service data</li>
                    <li>
                        Disconnect Gmail and revoke Google access (also via your Google Account
                        permissions)
                    </li>
                    <li>
                        Disconnect QuickBooks and revoke Intuit access (also via your Intuit
                        account connected apps)
                    </li>
                    <li>Object to or restrict certain processing, where applicable</li>
                </ul>
                <p>
                    You can update many settings in-product. For other requests, email{" "}
                    <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>. We may need to verify
                    your identity before responding. If you are in the EEA/UK, you may also lodge
                    a complaint with your local supervisory authority.
                </p>
            </LegalSection>

            <LegalSection id="international" title="10. International transfers">
                <p>
                    We and our processors may process data in the United States and other
                    countries. Where required, we use appropriate transfer mechanisms (such as
                    standard contractual clauses) with subprocessors.
                </p>
            </LegalSection>

            <LegalSection id="children" title="11. Children">
                <p>
                    The Service is not directed to children under 16 (or the minimum age required
                    in your jurisdiction). We do not knowingly collect personal information from
                    children. If you believe a child has provided us data, contact us and we will
                    delete it.
                </p>
            </LegalSection>

            <LegalSection id="cookies" title="12. Cookies and similar technologies">
                <p>
                    We use essential cookies and similar storage for authentication and session
                    security (for example access/refresh tokens). We do not use advertising trackers
                    as part of the core product experience described here. If that changes, we will
                    update this Policy.
                </p>
            </LegalSection>

            <LegalSection id="changes" title="13. Changes to this Policy">
                <p>
                    We may update this Privacy Policy to reflect product or legal changes. We will
                    post the revised Policy with a new “Last updated” date. Material changes may
                    also be communicated in-product or by email when appropriate.
                </p>
            </LegalSection>

            <LegalSection id="contact" title="14. Contact">
                <p>
                    Privacy: <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>
                    <br />
                    Support: <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
                </p>
            </LegalSection>
        </LegalShell>
    );
}
