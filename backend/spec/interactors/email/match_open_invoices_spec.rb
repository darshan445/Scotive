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

  def create_client!(external_id:, email:, domain:, name: nil)
    organization.clients.create!(
      integration: qbo,
      external_id: external_id,
      name: name || "Client #{external_id}",
      primary_email: email,
      domain: domain,
      associated_emails: [ email ]
    )
  end

  def create_invoice!(client_row, number:, amount:, due_date:, token: nil, issue_date: 20.days.ago.to_date, status: "invoiced")
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: number,
      invoice_number: number,
      issue_date: issue_date,
      due_date: due_date,
      total_amount: amount,
      balance_remaining: amount,
      pay_link_token: token,
      current_ar_status: status
    )
  end

  def mail(id:, thread_id:, from:, to:, subject:, body:, date: 2.days.ago.utc.iso8601)
    {
      "id" => id,
      "thread_id" => thread_id,
      "subject" => subject,
      "body" => body,
      "body_plain" => body,
      "date" => date,
      "from_attendee" => { "identifier" => from },
      "to_attendees" => [ { "identifier" => to } ],
      "cc_attendees" => []
    }
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

    result = described_class.execute(organization: organization, client: email_client)

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
        id: "m-home",
        thread_id: "t-home",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Invoice INV-808",
        body: "token tok-808"
      ),
      mail(
        id: "m-split",
        thread_id: "t-split",
        from: "owner@studio.com",
        to: "ap@acme.com",
        subject: "Fwd INV-808",
        body: "copy"
      )
    ])

    result = described_class.execute(organization: organization, client: email_client)

    expect(result).to be_success
    links = invoice.invoice_conversations.includes(:conversation).order(:created_at)
    expect(links.map { |row| [ row.conversation.external_thread_id, row.is_primary ] }).to contain_exactly(
      [ "t-home", true ],
      [ "t-split", false ]
    )
    expect(invoice.reload.current_ar_status).to eq("overdue")
    expect(invoice.invoice_state_transitions.last.trigger_source).to eq("clock_cron")
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

    result = described_class.execute(organization: organization, client: email_client)

    expect(result).to be_success
    expect(invoice.reload.current_ar_status).to eq("invoiced")
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

    result = described_class.execute(organization: organization, client: email_client)

    expect(result).to be_success
    expect(search_calls).to eq(2)
    expect(result.data.dig(:counts, :batches)).to eq(2)
    expect(result.data.dig(:counts, :clients)).to eq(11)
    expect(result.data.dig(:counts, :fallback_queued)).to eq(11)
    expect(Email::FindInvoiceThreadJob).to have_been_enqueued.exactly(11).times
  end

  it "uses any_email for Outlook instead of a Gmail search string" do
    mailbox.update!(provider: "outlook")
    client_row = create_client!(external_id: "4", email: "ap@acme.com", domain: "acme.com")
    create_invoice!(client_row, number: "INV-404", amount: 40, due_date: 5.days.from_now)
    stub_list([])

    result = described_class.execute(organization: organization, client: email_client)

    expect(result).to be_success
    expect(email_client).to have_received(:list_emails).with(
      hash_including(account_id: "acc-gmail", any_email: a_string_including("ap@acme.com"), search: nil)
    )
  end

  it "fails when mailbox is missing" do
    mailbox.update!(connection_status: "disconnected")

    result = described_class.execute(organization: organization, client: email_client)

    expect(result).not_to be_success
    expect(result.errors.to_s).to include("Connect Gmail or Outlook")
  end
end
