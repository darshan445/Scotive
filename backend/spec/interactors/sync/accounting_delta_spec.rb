# frozen_string_literal: true

require "rails_helper"

RSpec.describe Sync::AccountingDelta do
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
      connection_status: "connected",
      last_synced_at: 1.day.ago
    )
  end
  let(:qbo_client) { instance_double(Quickbooks::QuickbookClient) }

  after { clear_enqueued_jobs }

  it "upserts invoices changed since last_synced_at and advances the cursor" do
    allow(qbo_client).to receive(:query_invoices_updated_since).and_return([
      {
        "Id" => "201",
        "DocNumber" => "INV-201",
        "TxnDate" => "2026-09-10",
        "DueDate" => "2026-09-25",
        "TotalAmt" => 80,
        "Balance" => 80,
        "CustomerRef" => { "value" => "C9", "name" => "Beta" },
        "BillEmail" => { "Address" => "ap@beta.com" }
      }
    ])
    allow(qbo_client).to receive(:query_customers).and_return([
      { "Id" => "C9", "DisplayName" => "Beta", "PrimaryEmailAddr" => { "Address" => "ap@beta.com" } }
    ])
    allow(qbo_client).to receive(:get_invoice).and_return(
      "Id" => "201",
      "InvoiceLink" => "https://pay.example.com/inv/INV-201"
    )

    result = described_class.execute(organization: organization, client: qbo_client)
    expect(result.success?).to eq(true)
    expect(result.data[:created]).to eq(1)
    invoice = organization.invoices.find_by(external_id: "201")
    expect(invoice.invoice_number).to eq("INV-201")
    expect(invoice.pay_link_token).to eq("https://pay.example.com/inv/INV-201")
    expect(invoice.client.primary_email).to eq("ap@beta.com")
    expect(integration.reload.last_synced_at).to be_within(5.seconds).of(Time.current)
    expect(Email::FindInvoiceThreadJob).to have_been_enqueued.with(invoice.id)
  end

  it "syncs Xero invoices when a Xero integration is connected" do
    organization.integrations.create!(
      category: "accounting",
      provider: "xero",
      external_account_id: "tenant-1",
      account_name: "Studio",
      access_token: "at",
      refresh_token: "rt",
      token_expires_at: 1.hour.from_now,
      connection_status: "connected",
      last_synced_at: 1.day.ago
    )
    xero_client = instance_double(Xero::XeroClient)
    allow(qbo_client).to receive(:query_invoices_updated_since).and_return([])
    allow(qbo_client).to receive(:query_customers).and_return([])
    allow(xero_client).to receive(:query_invoices_updated_since).and_return([
      {
        "InvoiceID" => "inv-201",
        "InvoiceNumber" => "INV-201",
        "Type" => "ACCREC",
        "Status" => "AUTHORISED",
        "DateString" => "2026-09-10",
        "DueDateString" => "2026-09-25",
        "Total" => 80,
        "AmountDue" => 80,
        "Contact" => { "ContactID" => "c-9", "Name" => "Beta", "EmailAddress" => "ap@beta.com" },
        "OnlineInvoiceUrl" => "https://in.xero.com/INV-201"
      }
    ])
    allow(xero_client).to receive(:query_contacts).and_return([
      { "ContactID" => "c-9", "Name" => "Beta", "EmailAddress" => "ap@beta.com" }
    ])

    result = described_class.execute(organization: organization, client: qbo_client, xero_client: xero_client)
    expect(result.success?).to eq(true)
    expect(result.data[:created]).to eq(1)
    invoice = organization.invoices.find_by(external_id: "inv-201")
    expect(invoice.invoice_number).to eq("INV-201")
    expect(invoice.pay_link_token).to eq("https://in.xero.com/INV-201")
  end
end
