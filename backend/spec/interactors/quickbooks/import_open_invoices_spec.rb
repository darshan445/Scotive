# frozen_string_literal: true

require "rails_helper"

RSpec.describe Quickbooks::ImportOpenInvoices do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:integration) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Acme",
      access_token: "at",
      refresh_token: "rt",
      token_expires_at: 1.hour.from_now,
      connection_status: "connected"
    )
  end
  let(:qbo_client) { instance_double(Quickbooks::QuickbookClient) }

  def invoice_payload(id:, customer_id:, doc:, balance:, total:, txn_date:, due_date:, email: nil)
    {
      "Id" => id,
      "DocNumber" => doc,
      "TxnDate" => txn_date,
      "DueDate" => due_date,
      "TotalAmt" => total,
      "Balance" => balance,
      "CurrencyRef" => { "value" => "USD" },
      "CustomerRef" => { "value" => customer_id, "name" => "Acme Co" },
      "BillEmail" => { "Address" => email },
      "BillEmailCc" => { "Address" => "ap@acme.com" },
      "InvoiceLink" => "https://pay.example.com/inv/#{doc}"
    }
  end

  before { integration }

  it "upserts only invoice customers and sets last_synced_at" do
    allow(qbo_client).to receive(:query_open_invoices).and_return([
      invoice_payload(
        id: "101",
        customer_id: "58",
        doc: "INV-101",
        balance: "250.00",
        total: "250.00",
        txn_date: 10.days.ago.to_date.iso8601,
        due_date: 5.days.ago.to_date.iso8601,
        email: "billing@acme.com"
      )
    ])
    allow(qbo_client).to receive(:query_customers).and_return([
      {
        "Id" => "58",
        "DisplayName" => "Acme Co",
        "PrimaryEmailAddr" => { "Address" => "billing@acme.com" }
      }
    ])

    result = described_class.execute(organization: organization, client: qbo_client)

    expect(result).to be_success
    expect(result.data[:counts]).to eq(fetched: 1, created: 1, updated: 0, merged: 0)
    expect(qbo_client).to have_received(:query_customers).with(hash_including(ids: [ "58" ]))

    client_row = organization.clients.find_by!(external_id: "58")
    expect(client_row.name).to eq("Acme Co")
    expect(client_row.primary_email).to eq("billing@acme.com")
    expect(client_row.domain).to eq("acme.com")
    expect(client_row.associated_emails).to include("billing@acme.com", "ap@acme.com")

    invoice = organization.invoices.find_by!(external_id: "101")
    expect(invoice.invoice_number).to eq("INV-101")
    expect(invoice.books_status).to eq("open")
    expect(invoice.chase_status).to eq("watching")
    expect(invoice.list_bucket).to eq("auto_reminders")
    expect(invoice.pay_link_token).to eq("https://pay.example.com/inv/INV-101")
    expect(invoice.cc_emails).to eq([ "ap@acme.com" ])
    expect(integration.reload.last_synced_at).to be_present
  end

  it "puts a silent invoice past the Friendly window on Needs you" do
    allow(qbo_client).to receive(:query_open_invoices).and_return([
      invoice_payload(
        id: "109",
        customer_id: "58",
        doc: "INV-109",
        balance: "400.00",
        total: "400.00",
        txn_date: 20.days.ago.to_date.iso8601,
        due_date: 12.days.ago.to_date.iso8601,
        email: "billing@acme.com"
      )
    ])
    allow(qbo_client).to receive(:query_customers).and_return([
      { "Id" => "58", "DisplayName" => "Acme Co", "PrimaryEmailAddr" => { "Address" => "billing@acme.com" } }
    ])

    result = described_class.execute(organization: organization, client: qbo_client)

    expect(result).to be_success
    invoice = organization.invoices.find_by!(external_id: "109")
    expect(invoice.chase_status).to eq("needs_you")
    expect(invoice.list_bucket).to eq("needs_you")
    expect(invoice.invoice_chase_events.last.event_type).to eq("friendly_window_ended")
  end

  it "keeps books paid over a conversational overlay" do
    client_row = organization.clients.create!(
      integration: integration,
      external_id: "58",
      name: "Acme Co"
    )
    invoice = organization.invoices.create!(
      integration: integration,
      client: client_row,
      external_id: "101",
      invoice_number: "INV-101",
      issue_date: 20.days.ago,
      due_date: 10.days.ago,
      total_amount: 250,
      balance_remaining: 250,
      chase_status: "watching",
      expected_pay_date: Date.current
    )
    allow(qbo_client).to receive(:query_open_invoices).and_return([
      invoice_payload(
        id: "101",
        customer_id: "58",
        doc: "INV-101",
        balance: "0",
        total: "250.00",
        txn_date: 20.days.ago.to_date.iso8601,
        due_date: 10.days.ago.to_date.iso8601
      )
    ])
    allow(qbo_client).to receive(:query_customers).and_return([
      { "Id" => "58", "DisplayName" => "Acme Co" }
    ])

    result = described_class.execute(organization: organization, client: qbo_client)

    expect(result).to be_success
    expect(invoice.reload.books_status).to eq("paid")
    expect(invoice.expected_pay_date).to be_nil
    expect(invoice.invoice_chase_events.last.event_type).to eq("books_paid")
  end

  it "keeps an existing pay link when a later QBO payload omits InvoiceLink" do
    client_row = organization.clients.create!(
      integration: integration,
      external_id: "58",
      name: "Acme Co"
    )
    invoice = organization.invoices.create!(
      integration: integration,
      client: client_row,
      external_id: "101",
      invoice_number: "INV-101",
      issue_date: 20.days.ago,
      due_date: 10.days.ago,
      total_amount: 250,
      balance_remaining: 250,
      pay_link_token: "https://pay.example.com/inv/INV-101",
      books_status: "open"
    )
    payload = invoice_payload(
      id: "101",
      customer_id: "58",
      doc: "INV-101",
      balance: "250.00",
      total: "250.00",
      txn_date: 20.days.ago.to_date.iso8601,
      due_date: 10.days.ago.to_date.iso8601
    )
    payload.delete("InvoiceLink")
    allow(qbo_client).to receive(:query_open_invoices).and_return([ payload ])
    allow(qbo_client).to receive(:get_invoice).and_return(payload)
    allow(qbo_client).to receive(:query_customers).and_return([
      { "Id" => "58", "DisplayName" => "Acme Co" }
    ])

    result = described_class.execute(organization: organization, client: qbo_client)

    expect(result).to be_success
    expect(invoice.reload.pay_link_token).to eq("https://pay.example.com/inv/INV-101")
  end

  it "loads InvoiceLink from invoice GET when the query omits it" do
    payload = invoice_payload(
      id: "101",
      customer_id: "58",
      doc: "INV-101",
      balance: "250.00",
      total: "250.00",
      txn_date: 10.days.ago.to_date.iso8601,
      due_date: 5.days.ago.to_date.iso8601,
      email: "billing@acme.com"
    )
    payload.delete("InvoiceLink")
    url = "https://developer.intuit.com/comingSoon/scs-v1-29956e6ab4f9466a9974af4d6a5208d6f3c0b3ca31cc45e6a6c2f6464d42bb210a8ef3af47eb4022929574e5e19569ce-0?locale=en_US&cta=v3invoicelink"
    allow(qbo_client).to receive(:query_open_invoices).and_return([ payload ])
    allow(qbo_client).to receive(:get_invoice).and_return(payload.merge("InvoiceLink" => url))
    allow(qbo_client).to receive(:query_customers).and_return([
      { "Id" => "58", "DisplayName" => "Acme Co", "PrimaryEmailAddr" => { "Address" => "billing@acme.com" } }
    ])

    result = described_class.execute(organization: organization, client: qbo_client)

    expect(result).to be_success
    expect(organization.invoices.find_by!(external_id: "101").pay_link_token).to eq(url)
    expect(qbo_client).to have_received(:get_invoice).with(hash_including(id: "101"))
  end

  it "does not fetch customers when there are no open invoices" do
    allow(qbo_client).to receive(:query_open_invoices).and_return([])

    result = described_class.execute(organization: organization, client: qbo_client)

    expect(result).to be_success
    expect(result.data[:counts][:fetched]).to eq(0)
    expect(integration.reload.last_synced_at).to be_present
  end
end
