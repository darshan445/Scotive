# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::MatchOpenInvoices do
  include ActiveJob::TestHelper

  after { clear_enqueued_jobs }

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "at",
      connection_status: "connected",
      last_synced_at: 1.hour.ago
    )
  end
  let!(:mailbox) do
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
  end
  let(:email_client) { instance_double(Email::EmailClient) }
  let(:llm) { instance_double(Email::LlmClient) }

  def create_client!(external_id:, email:, domain:, name: nil, associated: nil)
    organization.clients.create!(
      integration: qbo,
      external_id: external_id,
      name: name || "Client #{external_id}",
      primary_email: email,
      domain: domain,
      associated_emails: associated || [ email ].compact
    )
  end

  def create_invoice!(client_row, number:, amount:, due_date:, token: nil, issue_date: 20.days.ago.to_date, status: "invoiced", balance: nil, cc_emails: [])
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: number,
      invoice_number: number,
      issue_date: issue_date,
      due_date: due_date,
      total_amount: amount,
      balance_remaining: balance.nil? ? amount : balance,
      pay_link_token: token,
      cc_emails: cc_emails,
      books_status: (status == "partial" ? "partial" : %w[paid voided].include?(status) ? status : "open"), chase_status: (%w[needs_you stopped].include?(status) ? status : "watching")
    )
  end

  def mail(id:, thread_id:, from:, to:, subject:, body:, date: 2.days.ago.utc.iso8601, cc: [], attachments: [])
    payload = {
      "id" => id,
      "thread_id" => thread_id,
      "subject" => subject,
      "body" => body,
      "body_plain" => body,
      "date" => date,
      "from_attendee" => { "identifier" => from },
      "to_attendees" => [ { "identifier" => to } ],
      "cc_attendees" => Array(cc).map { |email| { "identifier" => email } }
    }
    payload["attachments"] = Array(attachments).map { |name| { "name" => name } } if attachments.present?
    payload
  end

  def stub_list(items)
    allow(email_client).to receive(:list_emails) do |**kwargs|
      if kwargs[:limit] == 1 && kwargs[:after].blank? && kwargs[:search].blank? && kwargs[:any_email].blank?
        { "items" => [ { "id" => "head-msg" } ] }
      else
        { "items" => items }
      end
    end
  end

  def stub_intent(intent)
    allow(llm).to receive(:complete_json).and_return("intent" => intent)
  end

  def run_match
    described_class.execute(organization: organization, client: email_client, llm: llm)
  end

  def home_thread_id(invoice)
    invoice.invoice_conversations.includes(:conversation).find_by!(is_primary: true).conversation.external_thread_id
  end

  def split_thread_ids(invoice)
    invoice.invoice_conversations.includes(:conversation).where(is_primary: false).map { |row| row.conversation.external_thread_id }
  end

  def invoice_send_mail(invoice, date: 5.days.ago.utc.iso8601)
    mail(
      id: "m-send-#{invoice.invoice_number}",
      thread_id: "t-send-#{invoice.invoice_number}",
      from: "owner@studio.com",
      to: invoice.client.primary_email,
      subject: "Invoice #{invoice.invoice_number}",
      body: "Invoice #{invoice.invoice_number} is attached.",
      date: date
    )
  end

  it "matches pay-link token, invoice number, and exclusive amount" do
    token_client = create_client!(external_id: "1", email: "ap@acme.com", domain: "acme.com")
    number_client = create_client!(external_id: "2", email: "billing@beta.com", domain: "beta.com")
    amount_client = create_client!(external_id: "3", email: "books@gamma.com", domain: "gamma.com")
    token_invoice = create_invoice!(token_client, number: "INV-101", amount: 101, due_date: 5.days.from_now, token: "pay-101")
    number_invoice = create_invoice!(number_client, number: "INV-202", amount: 202, due_date: 5.days.from_now)
    amount_invoice = create_invoice!(amount_client, number: "INV-303", amount: 303.50, due_date: 5.days.from_now)

    stub_list([
      mail(
        id: "m-token",
        thread_id: "t-token",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice",
        body: "Pay here https://pay.example.com/pay-101"
      ),
      mail(
        id: "m-number",
        thread_id: "t-number",
        from: "owner@studio.com",
        to: "billing@beta.com",
        subject: "Re: INV-202",
        body: "Following up"
      ),
      mail(
        id: "m-amount",
        thread_id: "t-amount",
        from: "owner@studio.com",
        to: "books@gamma.com",
        subject: "Balance",
        body: "The remaining amount is $303.50."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(result.data[:queued]).to eq(false)
    expect(result.data.dig(:pipeline, :status)).to eq("complete")
    expect(token_invoice.conversations.find_by!(external_thread_id: "t-token").invoice_conversations.first).to be_is_primary
    expect(number_invoice.conversations.find_by!(external_thread_id: "t-number")).to be_present
    expect(amount_invoice.conversations.find_by!(external_thread_id: "t-amount")).to be_present
    expect(mailbox.reload.sync_cursor).to eq("head-msg")
    expect(email_client).to have_received(:list_emails).with(
      hash_including(account_id: "acc-gmail", search: a_string_including("after:", "from:ap@acme.com", "to:acme.com"))
    )
    expect(result.data.dig(:counts, :fallback_queued)).to eq(0)
    expect(Email::FindInvoiceThreadJob).not_to have_been_enqueued
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end

  it "links extra matching threads as split and clocks outbound-only overdue invoices" do
    client_row = create_client!(external_id: "8", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(
      client_row,
      number: "INV-808",
      amount: 808,
      due_date: 3.days.ago,
      token: "tok-808",
      status: "invoiced"
    )
    stub_list([
      mail(
        id: "m-split",
        thread_id: "t-split",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Fwd INV-808",
        body: "copy",
        date: 1.day.ago.utc.iso8601
      ),
      mail(
        id: "m-home",
        thread_id: "t-home",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice INV-808",
        body: "token tok-808",
        date: 4.days.ago.utc.iso8601
      )
    ])

    result = run_match

    expect(result).to be_success
    links = invoice.invoice_conversations.includes(:conversation).order(:created_at)
    expect(links.map { |row| [ row.conversation.external_thread_id, row.is_primary ] }).to contain_exactly(
      [ "t-home", true ],
      [ "t-split", false ]
    )
    expect(invoice.reload.books_status).to eq("open")
    expect(invoice.chase_status).to eq("watching")
    expect(Message.joins(:conversation).where(conversations: { organization_id: organization.id }).pluck(:direction).uniq).to eq([ "user_to_client" ])
  end

  it "does not clock invoices that already have a client reply" do
    client_row = create_client!(external_id: "9", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "INV-909", amount: 90, due_date: 5.days.from_now)
    stub_list([
      mail(
        id: "m-in",
        thread_id: "t-in",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "INV-909",
        body: "We got it"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.reload.books_status).to eq("open")
    expect(invoice.reload.conversations.first.messages.first.direction).to eq("client_to_user")
    expect(result.data.dig(:counts, :ai_queued)).to eq(1)
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(invoice.id)
  end

  it "searches clients in batches of 10" do
    11.times do |index|
      row = create_client!(external_id: (index + 1).to_s, email: "ap#{index}@acme.com", domain: "acme.com")
      create_invoice!(row, number: "INV-#{1000 + index}", amount: 50 + index, due_date: 5.days.from_now)
    end
    search_calls = 0
    allow(email_client).to receive(:list_emails) do |**kwargs|
      if kwargs[:search].present?
        search_calls += 1
        { "items" => [] }
      else
        { "items" => [ { "id" => "head-msg" } ] }
      end
    end

    result = run_match

    expect(result).to be_success
    expect(search_calls).to eq(2)
    expect(result.data.dig(:counts, :batches)).to eq(2)
    expect(result.data.dig(:counts, :clients)).to eq(11)
    expect(result.data.dig(:counts, :fallback_queued)).to eq(11)
    expect(Email::FindInvoiceThreadJob).to have_been_enqueued.exactly(11).times
  end

  it "links every open invoice referenced on one shared thread" do
    client_row = create_client!(external_id: "12", email: "ap@acme.com", domain: "acme.com")
    first = create_invoice!(client_row, number: "SIM-2001", amount: 1000, due_date: 5.days.ago, status: "overdue")
    second = create_invoice!(client_row, number: "SIM-2003", amount: 2500, due_date: 3.days.ago, status: "overdue")
    stub_list([
      mail(
        id: "m-qbo-2001",
        thread_id: "t-qbo",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Re: Invoice from Studio",
        body: "We only owe $800.\nOn Mon wrote:\nInvoice SIM-2001 for $1,000.00"
      ).merge("attachments" => [ { "name" => "Invoice_SIM-2001.pdf" } ]),
      mail(
        id: "m-qbo-2003",
        thread_id: "t-qbo",
        from: "quickbooks@notification.intuit.com",
        to: "ap@acme.com",
        subject: "Invoice from Studio",
        body: "Your invoice is attached."
      ).merge("attachments" => [ { "name" => "Invoice_SIM-2003.pdf" } ])
    ])

    result = run_match

    expect(result).to be_success
    expect(first.conversations.find_by(external_thread_id: "t-qbo")).to be_present
    expect(second.conversations.find_by(external_thread_id: "t-qbo")).to be_present
    expect(first.reload.books_status).to eq("open")
    expect(Email::FindInvoiceThreadJob).not_to have_been_enqueued
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(first.id)
  end

  it "does not attach a thread whose subject names a different invoice" do
    client_row = create_client!(external_id: "14", email: "ap@acme.com", domain: "acme.com")
    first = create_invoice!(client_row, number: "SIM-2002", amount: 500, due_date: 10.days.from_now)
    second = create_invoice!(client_row, number: "SIM-2008", amount: 900, due_date: 2.days.from_now)
    remittance_a = create_invoice!(client_row, number: "SIM-2003", amount: 2500, due_date: 3.days.ago, status: "overdue")
    stub_list([
      mail(
        id: "m-2008",
        thread_id: "t-2008",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Invoice SIM-2008 from Craig's Design and Landscaping Services",
        body: "We just sent an initial deposit of $400.00 via direct deposit. We will transfer the remaining $500.00 at the end of the month."
      ),
      mail(
        id: "m-2002",
        thread_id: "t-2002",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice SIM-2002 from Craig's Design and Landscaping Services",
        body: "Your invoice is attached."
      ),
      mail(
        id: "m-both",
        thread_id: "t-remit",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Consolidated Remittance Advice: SIM-2003 & SIM-2002",
        body: "Combined payment for invoice SIM-2002 ($500) and invoice SIM-2003 ($2,500)."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(first.conversations.find_by(external_thread_id: "t-2002")).to be_present
    expect(first.conversations.find_by(external_thread_id: "t-remit")).to be_present
    expect(first.conversations.find_by(external_thread_id: "t-2008")).to be_blank
    expect(second.conversations.find_by(external_thread_id: "t-2008")).to be_present
    expect(second.conversations.find_by(external_thread_id: "t-2002")).to be_blank
    expect(remittance_a.conversations.find_by(external_thread_id: "t-remit")).to be_present
  end

  it "keeps the oldest owner send as HOME when a later owner reply also quotes the number" do
    client_row = create_client!(external_id: "19", email: "ap@acme.com", domain: "acme.com")
    first = create_invoice!(client_row, number: "SIM-2102", amount: 500, due_date: 10.days.from_now)
    second = create_invoice!(client_row, number: "SIM-2103", amount: 2500, due_date: 3.days.ago, status: "overdue")
    stub_list([
      mail(
        id: "m-remit-client",
        thread_id: "t-remit",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Consolidated Remittance Advice: SIM-2103 & SIM-2102",
        body: "Combined payment for invoice SIM-2102 ($500) and invoice SIM-2103 ($2,500).",
        date: 2.days.ago.utc.iso8601
      ),
      mail(
        id: "m-remit-owner",
        thread_id: "t-remit",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Re: Consolidated Remittance Advice: SIM-2103 & SIM-2102",
        body: "Thanks, I will monitor our account for both transactions.",
        date: 1.day.ago.utc.iso8601
      ),
      mail(
        id: "m-2103-send",
        thread_id: "t-2103",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice SIM-2103 from Studio",
        body: "Your invoice is attached.",
        date: 5.days.ago.utc.iso8601
      ),
      mail(
        id: "m-2102-send",
        thread_id: "t-2102",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice SIM-2102 from Studio",
        body: "Your invoice is attached.",
        date: 6.days.ago.utc.iso8601
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(home_thread_id(first)).to eq("t-2102")
    expect(home_thread_id(second)).to eq("t-2103")
    expect(split_thread_ids(first)).to contain_exactly("t-remit")
    expect(split_thread_ids(second)).to contain_exactly("t-remit")
  end

  it "inherits a whole thread from one invoice number mention" do
    client_row = create_client!(external_id: "16", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2002", amount: 500, due_date: 10.days.from_now)
    stub_list([
      mail(
        id: "m-1",
        thread_id: "t-home",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice SIM-2002 from Studio",
        body: "Your invoice is attached."
      ),
      mail(
        id: "m-2",
        thread_id: "t-home",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Re: Invoice SIM-2002 from Studio",
        body: "Wire sent."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-home")).to be_present
    expect(invoice.conversations.find_by(external_thread_id: "t-home").messages.count).to eq(2)
  end

  it "joint-links an unlabeled payment thread to every open invoice for that client" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "15", email: "ap@acme.com", domain: "acme.com")
    first = create_invoice!(client_row, number: "SIM-2002", amount: 500, due_date: 10.days.from_now)
    second = create_invoice!(client_row, number: "SIM-2003", amount: 2500, due_date: 3.days.ago, status: "overdue")
    stub_list([
      invoice_send_mail(first),
      invoice_send_mail(second),
      mail(
        id: "m-both",
        thread_id: "t-orphan",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Payment released",
        body: "We will pay both outstanding invoices this week."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(first.conversations.find_by(external_thread_id: "t-orphan")).to be_present
    expect(second.conversations.find_by(external_thread_id: "t-orphan")).to be_present
    expect(llm).to have_received(:complete_json)
  end

  it "does not joint-link unlabeled payment to a never-sent invoice" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "41", email: "ap@acme.com", domain: "acme.com")
    sent = create_invoice!(client_row, number: "SIM-2201", amount: 205, due_date: 4.days.ago)
    never = create_invoice!(client_row, number: "SIM-2202", amount: 215, due_date: 2.days.ago)
    stub_list([
      invoice_send_mail(sent),
      mail(
        id: "m-pay",
        thread_id: "t-pay",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Payment released",
        body: "We will pay the outstanding invoices this week."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(sent.conversations.find_by(external_thread_id: "t-pay")).to be_present
    expect(never.conversations.find_by(external_thread_id: "t-pay")).to be_blank
  end

  it "does not joint-link unlabeled payment to an invoice issued after that email" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "42", email: "ap@acme.com", domain: "acme.com")
    prior = create_invoice!(client_row, number: "SIM-2101", amount: 1000, due_date: 5.days.ago, issue_date: 20.days.ago.to_date)
    later = create_invoice!(client_row, number: "SIM-2301", amount: 325, due_date: 1.day.ago, issue_date: Date.current)
    stub_list([
      invoice_send_mail(prior, date: 10.days.ago.utc.iso8601),
      invoice_send_mail(later, date: 1.hour.ago.utc.iso8601),
      mail(
        id: "m-old-pay",
        thread_id: "t-old-pay",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Payment released",
        body: "We will pay the outstanding invoices this week.",
        date: 2.days.ago.utc.iso8601
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(prior.conversations.find_by(external_thread_id: "t-old-pay")).to be_present
    expect(later.conversations.find_by(external_thread_id: "t-old-pay")).to be_blank
  end

  it "does not bind an exclusive amount to an invoice that did not exist at that email" do
    client_row = create_client!(external_id: "43", email: "ap@acme.com", domain: "acme.com")
    first = create_invoice!(client_row, number: "SIM-2104", amount: 350, due_date: 12.days.ago, issue_date: 20.days.ago.to_date)
    later = create_invoice!(client_row, number: "SIM-2404", amount: 350, due_date: 1.day.from_now, issue_date: Date.current)
    stub_list([
      mail(
        id: "m-amt",
        thread_id: "t-amt",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Balance question",
        body: "Accounting asked about the $350.00 balance.",
        date: 2.days.ago.utc.iso8601
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(first.conversations.find_by(external_thread_id: "t-amt")).to be_present
    expect(later.conversations.find_by(external_thread_id: "t-amt")).to be_blank
  end

  it "links an unlabeled payment thread to the only open invoice" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "13", email: "ap@acme.com", domain: "acme.com")
    leftover = create_invoice!(client_row, number: "SIM-2001", amount: 1000, due_date: 5.days.ago, status: "overdue")
    stub_list([
      invoice_send_mail(leftover),
      mail(
        id: "m-dispute",
        thread_id: "t-qbo-replies",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Re: Invoice from Craig's Design",
        body: "Wait, stop the payment! We only owe $800."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(leftover.conversations.find_by(external_thread_id: "t-qbo-replies")).to be_present
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(leftover.id)
  end

  it "does not leftover-attach a numbered sibling thread to another invoice" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "17", email: "ap@acme.com", domain: "acme.com")
    unmatched = create_invoice!(client_row, number: "SIM-2007", amount: 600, due_date: 8.days.ago, status: "overdue")
    sibling = create_invoice!(client_row, number: "SIM-2010", amount: 450, due_date: 6.days.from_now)
    stub_list([
      mail(
        id: "m-2010",
        thread_id: "t-2010",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice SIM-2010 from Craig's Design and Landscaping Services",
        body: "Your invoice is attached."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(sibling.conversations.find_by(external_thread_id: "t-2010")).to be_present
    expect(unmatched.conversations.find_by(external_thread_id: "t-2010")).to be_blank
  end

  it "skips unlabeled threads the reader does not treat as invoice payment" do
    stub_intent("unrelated")
    client_row = create_client!(external_id: "18", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2001", amount: 1000, due_date: 5.days.ago, status: "overdue")
    stub_list([
      mail(
        id: "m-chat",
        thread_id: "t-chat",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Kickoff",
        body: "Can we move the workshop to Tuesday?"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-chat")).to be_blank
    expect(result.data.dig(:counts, :fallback_queued)).to eq(1)
  end

  it "uses any_email for Outlook instead of a Gmail search string" do
    mailbox.update!(provider: "outlook")
    client_row = create_client!(external_id: "4", email: "ap@acme.com", domain: "acme.com")
    create_invoice!(client_row, number: "INV-404", amount: 40, due_date: 5.days.from_now)
    stub_list([])

    result = run_match

    expect(result).to be_success
    expect(email_client).to have_received(:list_emails).with(
      hash_including(account_id: "acc-gmail", any_email: a_string_including("ap@acme.com"), search: nil)
    )
  end

  it "fails when mailbox is missing" do
    mailbox.update!(connection_status: "disconnected")

    result = run_match

    expect(result).not_to be_success
    expect(result.errors.to_s).to include("Connect Gmail or Outlook")
  end

  it "binds a thread that only uses the trailing digits of the invoice number" do
    client_row = create_client!(external_id: "21", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2111", amount: 175, due_date: 4.days.from_now)
    sibling = create_invoice!(client_row, number: "SIM-2101", amount: 1000, due_date: 5.days.ago, status: "overdue")
    stub_list([
      mail(
        id: "m-digits",
        thread_id: "t-digits",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Checking 2111",
        body: "AP asked about 2111 — is that still open?"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-digits")).to be_present
    expect(sibling.conversations.find_by(external_thread_id: "t-digits")).to be_blank
  end

  it "uses a pay-link token on an owner send that has no invoice number as HOME" do
    client_row = create_client!(external_id: "22", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2116", amount: 220, due_date: 3.days.ago, token: "paytok-zz91ab", status: "invoiced")
    stub_list([
      mail(
        id: "m-token-home",
        thread_id: "t-token-home",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Your invoice is ready",
        body: "Pay here https://connect.intuit.com/pay/paytok-zz91ab"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(home_thread_id(invoice)).to eq("t-token-home")
    expect(invoice.reload.books_status).to eq("open")
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end

  it "binds an inbound that quotes a pay-link identity to that invoice only" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "23", email: "ap@acme.com", domain: "acme.com")
    first = create_invoice!(client_row, number: "SIM-2116", amount: 220, due_date: 3.days.ago, token: "paytok-aa91ab", status: "overdue")
    second = create_invoice!(client_row, number: "SIM-2117", amount: 330, due_date: 2.days.from_now, token: "paytok-bb91ab")
    stub_list([
      mail(
        id: "m-token-in",
        thread_id: "t-token-in",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Link question",
        body: "Is https://connect.intuit.com/pay/paytok-aa91ab still the right pay page?"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(first.conversations.find_by(external_thread_id: "t-token-in")).to be_present
    expect(second.conversations.find_by(external_thread_id: "t-token-in")).to be_blank
    expect(llm).not_to have_received(:complete_json)
  end

  it "uses a QBO-style pay URL with a generic path as HOME when the send has no invoice number" do
    url = "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=a1b2c3d4-e5f6-4780-ab12-cdef34567890"
    client_row = create_client!(external_id: "32", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2201", amount: 205, due_date: 4.days.ago, token: url, status: "invoiced")
    stub_list([
      mail(
        id: "m-qbo-link",
        thread_id: "t-qbo-link",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Your invoice is ready",
        body: "Pay here: #{url}"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(home_thread_id(invoice)).to eq("t-qbo-link")
    expect(invoice.reload.books_status).to eq("open")
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end

  it "reads a pay URL from an HTML href when the visible body has no number" do
    url = "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=b2c3d4e5-f6a7-4890-bc23-def456789012"
    client_row = create_client!(external_id: "33", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2203", amount: 240, due_date: 2.days.ago, token: url, status: "invoiced")
    stub_list([
      mail(
        id: "m-href",
        thread_id: "t-href",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Your invoice is ready",
        body: %(<p>View and pay this invoice</p><a href="#{url}">Pay now</a>)
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(home_thread_id(invoice)).to eq("t-href")
  end

  it "does not bind a thread just because a stored pay token is a generic word" do
    stub_intent("other_payment")
    client_row = create_client!(external_id: "35", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2205", amount: 260, due_date: 3.days.from_now, token: "invoice")
    stub_list([
      mail(
        id: "m-generic",
        thread_id: "t-generic",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Workshop Thursday",
        body: "The invoice workshop is Thursday. This is not a payment."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-generic")).to be_blank
    expect(result.data.dig(:counts, :fallback_queued)).to eq(1)
  end

  it "skips an unlabeled automatic-reply subject and leaves the invoice for fallback" do
    stub_intent("invoice_payment")
    client_row = create_client!(external_id: "24", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2113", amount: 410, due_date: 1.day.from_now)
    stub_list([
      mail(
        id: "m-ooo",
        thread_id: "t-ooo",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Out of Office: back Monday",
        body: "I am out of the office with no access to email."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-ooo")).to be_blank
    expect(result.data.dig(:counts, :fallback_queued)).to eq(1)
    expect(Email::FindInvoiceThreadJob).to have_been_enqueued.with(invoice.id)
    expect(llm).not_to have_received(:complete_json)
  end

  it "does not attach unlabeled other_payment talk (new quote / project budget)" do
    stub_intent("other_payment")
    client_row = create_client!(external_id: "25", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2114", amount: 480, due_date: 6.days.from_now)
    stub_list([
      mail(
        id: "m-quote",
        thread_id: "t-quote",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Quote for the spring add-on",
        body: "Can you send a new estimate? Budget for next quarter is about $4,000 — not related to anything already billed."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-quote")).to be_blank
    expect(result.data.dig(:counts, :fallback_queued)).to eq(1)
  end

  it "excludes paid, voided, and zero-balance invoices from match" do
    client_row = create_client!(external_id: "26", email: "ap@acme.com", domain: "acme.com")
    paid = create_invoice!(client_row, number: "SIM-PAID", amount: 90, due_date: 1.day.ago, status: "paid", balance: 0)
    voided = create_invoice!(client_row, number: "SIM-VOID", amount: 80, due_date: 1.day.ago, status: "voided", balance: 80)
    open_row = create_invoice!(client_row, number: "SIM-OPEN", amount: 70, due_date: 2.days.from_now)
    stub_list([
      mail(
        id: "m-paid",
        thread_id: "t-paid",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "SIM-PAID and SIM-VOID and SIM-OPEN",
        body: "Please confirm SIM-PAID, SIM-VOID, and SIM-OPEN."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(open_row.conversations.find_by(external_thread_id: "t-paid")).to be_present
    expect(paid.conversations.find_by(external_thread_id: "t-paid")).to be_blank
    expect(voided.conversations.find_by(external_thread_id: "t-paid")).to be_blank
    expect(Email::FindInvoiceThreadJob).not_to have_been_enqueued
  end

  it "matches mail from a CC / AP alias stored on the invoice" do
    client_row = create_client!(external_id: "27", email: "ap@acme.com", domain: "acme.com", associated: [ "ap@acme.com" ])
    invoice = create_invoice!(client_row, number: "SIM-2118", amount: 640, due_date: 3.days.from_now, cc_emails: [ "cpa@books.com" ])
    stub_list([
      mail(
        id: "m-cpa",
        thread_id: "t-cpa",
        from: "cpa@books.com",
        to: "owner@studio.com",
        subject: "SIM-2118 from the books team",
        body: "We have SIM-2118 in the pay run.",
        cc: [ "ap@acme.com" ]
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-cpa")).to be_present
    expect(email_client).to have_received(:list_emails).with(
      hash_including(search: a_string_including("from:cpa@books.com"))
    )
  end

  it "matches a corporate-domain coworker who is not the primary email" do
    client_row = create_client!(external_id: "28", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2119", amount: 255, due_date: 4.days.from_now)
    stub_list([
      mail(
        id: "m-domain",
        thread_id: "t-domain",
        from: "billing@acme.com",
        to: "owner@studio.com",
        subject: "SIM-2119",
        body: "Finance has SIM-2119."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-domain")).to be_present
    expect(email_client).to have_received(:list_emails).with(
      hash_including(search: a_string_including("from:acme.com", "to:acme.com"))
    )
  end

  it "does not search the owner's mailbox as if it were a client contact" do
    client_row = create_client!(
      external_id: "29a",
      email: "r24827708@gmail.com",
      domain: nil,
      associated: [ "r24827708@gmail.com", "owner@studio.com" ]
    )
    create_invoice!(client_row, number: "1081", amount: 50, due_date: 29.days.from_now)
    stub_list([])

    result = run_match

    expect(result).to be_success
    expect(email_client).to have_received(:list_emails).with(
      hash_including(search: a_string_including("from:r24827708@gmail.com"))
    )
    expect(email_client).not_to have_received(:list_emails).with(
      hash_including(search: a_string_including("from:owner@studio.com"))
    )
  end

  it "does not bind a newsletter that only mentions a bare invoice number in HTML" do
    client_row = create_client!(external_id: "29b", email: "r24827708@gmail.com", domain: nil)
    invoice = create_invoice!(client_row, number: "1081", amount: 50, due_date: 29.days.from_now)
    stub_intent("other_payment")
    stub_list([
      mail(
        id: "m-promo",
        thread_id: "t-promo",
        from: "noreply@email.openai.com",
        to: "owner@studio.com",
        subject: "4 new image styles to try",
        body: "<img width=\"1081\" /><p>See your photos in a new way. Only 50 people left.</p>"
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-promo")).to be_blank
  end

  it "searches a Gmail client by exact address, not from:gmail.com" do
    client_row = create_client!(external_id: "29", email: "vt444713@gmail.com", domain: nil)
    create_invoice!(client_row, number: "SIM-GMAIL", amount: 15, due_date: 5.days.from_now)
    stub_list([])

    result = run_match

    expect(result).to be_success
    expect(email_client).to have_received(:list_emails).with(
      hash_including(search: a_string_including("from:vt444713@gmail.com"))
    )
    expect(email_client).not_to have_received(:list_emails).with(
      hash_including(search: a_string_including("from:gmail.com "))
    )
  end

  it "Pass-1 matches a number that only lives in quoted reply text or the PDF filename" do
    client_row = create_client!(external_id: "30", email: "ap@acme.com", domain: "acme.com")
    invoice = create_invoice!(client_row, number: "SIM-2115", amount: 195, due_date: 2.days.from_now)
    stub_list([
      mail(
        id: "m-quoted",
        thread_id: "t-quoted",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Invoice from Studio",
        body: "Got it.\nOn Mon, QBO wrote:\nInvoice SIM-2115 for $195.00 is attached.",
        attachments: [ "Invoice_SIM-2115.pdf" ]
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-quoted")).to be_present
  end

  it "clocks an outbound-only send and queues FindInvoiceThread when nothing matches" do
    client_row = create_client!(external_id: "31", email: "ap@acme.com", domain: "acme.com")
    clocked = create_invoice!(client_row, number: "SIM-2201", amount: 50, due_date: 4.days.ago, status: "invoiced")
    missed = create_invoice!(client_row, number: "SIM-2202", amount: 60, due_date: 2.days.ago, status: "invoiced")
    stub_list([
      mail(
        id: "m-clock",
        thread_id: "t-clock",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice SIM-2201 from Studio",
        body: "Your invoice is attached."
      )
    ])

    result = run_match

    expect(result).to be_success
    expect(clocked.reload.books_status).to eq("open")
    expect(clocked.conversations.find_by(external_thread_id: "t-clock")).to be_present
    expect(missed.conversations).to be_empty
    expect(result.data.dig(:counts, :fallback_queued)).to eq(1)
    expect(Email::FindInvoiceThreadJob).to have_been_enqueued.with(missed.id)
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end
end
