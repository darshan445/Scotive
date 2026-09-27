# frozen_string_literal: true

require "rails_helper"

RSpec.describe Xero::ApplyWebhook do
  include ActiveJob::TestHelper

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let!(:integration) do
    organization.integrations.create!(
      category: "accounting",
      provider: "xero",
      external_account_id: "tenant-1",
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
      external_id: "c-1",
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
      external_id: "inv-95",
      invoice_number: "INV-95",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 400,
      balance_remaining: 400,
      books_status: "open"
    )
  end
  let(:xero_client) { instance_double(Xero::XeroClient) }

  def event_for(resource_id:, event_type: "UPDATE")
    WebhookEvent.create!(
      organization: organization,
      integration: integration,
      provider: "xero",
      external_event_id: "xero:tenant-1:#{resource_id}:#{event_type}:1",
      payload: {
        "tenantId" => "tenant-1",
        "resourceId" => resource_id,
        "eventCategory" => "INVOICE",
        "eventType" => event_type
      },
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
    allow(xero_client).to receive(:get_invoice).and_return(
      "InvoiceID" => "inv-95",
      "InvoiceNumber" => "INV-95",
      "Type" => "ACCREC",
      "Status" => "PAID",
      "DateString" => "2026-08-01",
      "DueDateString" => "2026-09-01",
      "Total" => 400,
      "AmountDue" => 0,
      "Contact" => { "ContactID" => "c-1", "Name" => "Acme", "EmailAddress" => "ap@acme.com" }
    )
    allow(xero_client).to receive(:get_online_invoice_url).and_return(nil)
    allow(xero_client).to receive(:get_contact).and_return(
      "ContactID" => "c-1",
      "Name" => "Acme",
      "EmailAddress" => "ap@acme.com"
    )

    result = described_class.execute(webhook_event: event_for(resource_id: "inv-95"), client: xero_client)

    expect(result.success?).to eq(true)
    invoice.reload
    expect(invoice.books_status).to eq("paid")
    expect(invoice.balance_remaining).to eq(0)
    expect(OutboxMessage.last.status).to eq("cancelled")
    expect(OutboxMessage.last.cancellation_reason).to eq("paid_in_books")
  end

  it "upserts a new invoice and searches for its thread" do
    allow(xero_client).to receive(:get_invoice).and_return(
      "InvoiceID" => "inv-581",
      "InvoiceNumber" => "1062",
      "Type" => "ACCREC",
      "Status" => "AUTHORISED",
      "DateString" => "2026-09-12",
      "DueDateString" => "2026-09-25",
      "Total" => 3240,
      "AmountDue" => 3240,
      "Contact" => { "ContactID" => "c-1", "Name" => "Acme", "EmailAddress" => "ap@acme.com" },
      "OnlineInvoiceUrl" => "https://in.xero.com/abc"
    )
    allow(xero_client).to receive(:get_contact).and_return(
      "ContactID" => "c-1",
      "Name" => "Acme",
      "EmailAddress" => "ap@acme.com"
    )

    result = nil
    expect {
      result = described_class.execute(
        webhook_event: event_for(resource_id: "inv-581", event_type: "CREATE"),
        client: xero_client
      )
    }.to have_enqueued_job(Email::FindInvoiceThreadJob)

    expect(result.success?).to eq(true)
    created = organization.invoices.find_by!(external_id: "inv-581")
    expect(created.invoice_number).to eq("1062")
    expect(created.pay_link_token).to eq("https://in.xero.com/abc")
    expect(result.data[:created]).to eq(true)
  end

  it "voids a VOIDED invoice" do
    allow(xero_client).to receive(:get_invoice).and_return(
      "InvoiceID" => "inv-95",
      "Type" => "ACCREC",
      "Status" => "VOIDED",
      "Contact" => { "ContactID" => "c-1" }
    )

    result = described_class.execute(webhook_event: event_for(resource_id: "inv-95"), client: xero_client)

    expect(result.success?).to eq(true)
    expect(invoice.reload.books_status).to eq("voided")
  end
end
