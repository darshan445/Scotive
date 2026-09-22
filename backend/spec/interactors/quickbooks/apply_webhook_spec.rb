# frozen_string_literal: true

require "rails_helper"

RSpec.describe Quickbooks::ApplyWebhook do
  include ActiveJob::TestHelper

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let!(:integration) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "at",
      refresh_token: "rt",
      token_expires_at: 1.hour.from_now,
      connection_status: "connected"
    )
  end
  let(:client_row) do
    organization.clients.create!(
      integration: integration,
      external_id: "C1",
      name: "Acme",
      primary_email: "ap@acme.com",
      domain: "acme.com",
      associated_emails: [ "ap@acme.com" ]
    )
  end
  let!(:invoice) do
    organization.invoices.create!(
      integration: integration,
      client: client_row,
      external_id: "95",
      invoice_number: "INV-95",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 400,
      balance_remaining: 400,
      current_ar_status: "overdue"
    )
  end
  let(:qbo_client) { instance_double(Quickbooks::QuickbookClient) }

  def event_for(name:, id:, operation: "Update")
    WebhookEvent.create!(
      organization: organization,
      integration: integration,
      provider: "qbo",
      external_event_id: "qbo:realm-1:#{name}:#{id}:#{operation}:1",
      payload: { "realmId" => "realm-1", "name" => name, "id" => id, "operation" => operation },
      status: "pending",
      created_at: Time.current
    )
  end

  after { clear_enqueued_jobs }

  it "marks an invoice paid from books and cancels scheduled outbox" do
    OutboxMessage.create!(
      organization: organization,
      invoice: invoice,
      to_address: "ap@acme.com",
      subject: "Reminder",
      body: "Please pay",
      status: "scheduled",
      scheduled_send_at: 1.hour.from_now
    )
    allow(qbo_client).to receive(:get_invoice).and_return(
      "Id" => "95",
      "DocNumber" => "INV-95",
      "TxnDate" => "2026-08-01",
      "DueDate" => "2026-09-01",
      "TotalAmt" => 400,
      "Balance" => 0,
      "CustomerRef" => { "value" => "C1", "name" => "Acme" },
      "BillEmail" => { "Address" => "ap@acme.com" }
    )
    allow(qbo_client).to receive(:get_customer).and_return(
      "Id" => "C1",
      "DisplayName" => "Acme",
      "PrimaryEmailAddr" => { "Address" => "ap@acme.com" }
    )

    result = described_class.execute(webhook_event: event_for(name: "Invoice", id: "95"), client: qbo_client)

    expect(result.success?).to eq(true)
    invoice.reload
    expect(invoice.current_ar_status).to eq("paid")
    expect(invoice.balance_remaining).to eq(0)
    expect(invoice.invoice_state_transitions.last.trigger_source).to eq("books_webhook")
    expect(OutboxMessage.last.status).to eq("cancelled")
    expect(OutboxMessage.last.cancellation_reason).to eq("paid_in_books")
  end

  it "persists InvoiceLink from the invoice GET" do
    url = "https://developer.intuit.com/comingSoon/scs-v1-abc"
    allow(qbo_client).to receive(:get_invoice).and_return(
      "Id" => "95",
      "DocNumber" => "INV-95",
      "TxnDate" => "2026-08-01",
      "DueDate" => "2026-09-01",
      "TotalAmt" => 400,
      "Balance" => 400,
      "CustomerRef" => { "value" => "C1", "name" => "Acme" },
      "BillEmail" => { "Address" => "ap@acme.com" },
      "InvoiceLink" => url
    )
    allow(qbo_client).to receive(:get_customer).and_return(
      "Id" => "C1",
      "DisplayName" => "Acme",
      "PrimaryEmailAddr" => { "Address" => "ap@acme.com" }
    )

    result = described_class.execute(webhook_event: event_for(name: "Invoice", id: "95"), client: qbo_client)

    expect(result.success?).to eq(true)
    expect(invoice.reload.pay_link_token).to eq(url)
  end

  it "voids a deleted invoice" do
    result = described_class.execute(
      webhook_event: event_for(name: "Invoice", id: "95", operation: "Delete"),
      client: qbo_client
    )
    expect(result.success?).to eq(true)
    expect(invoice.reload.current_ar_status).to eq("voided")
  end

  it "marks the QBO integration for reauth when tokens cannot be decrypted" do
    allow_any_instance_of(Integration).to receive(:access_token)
      .and_raise(ActiveRecord::Encryption::Errors::Decryption)

    result = described_class.execute(
      webhook_event: event_for(name: "Invoice", id: "95"),
      client: qbo_client
    )

    expect(result.success?).to eq(false)
    expect(result.errors).to match(/decrypt/)
    expect(integration.reload.connection_status).to eq("reauth_required")
  end
end
