# frozen_string_literal: true

require "rails_helper"

RSpec.describe Xero::ImportOpenInvoices do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:integration) do
    organization.integrations.create!(
      category: "accounting",
      provider: "xero",
      external_account_id: "tenant-1",
      account_name: "Acme",
      access_token: "at",
      refresh_token: "rt",
      token_expires_at: 1.hour.from_now,
      connection_status: "connected"
    )
  end
  let(:xero_client) { instance_double(Xero::XeroClient) }

  def invoice_payload(id:, contact_id:, number:, balance:, total:, date:, due_date:, email: nil)
    {
      "InvoiceID" => id,
      "InvoiceNumber" => number,
      "Type" => "ACCREC",
      "Status" => "AUTHORISED",
      "DateString" => date,
      "DueDateString" => due_date,
      "Total" => total,
      "AmountDue" => balance,
      "CurrencyCode" => "USD",
      "Contact" => { "ContactID" => contact_id, "Name" => "Acme Co", "EmailAddress" => email },
      "OnlineInvoiceUrl" => "https://in.xero.com/#{number}"
    }
  end

  before { integration }

  it "upserts only invoice contacts and sets last_synced_at" do
    allow(xero_client).to receive(:query_open_invoices).and_return([
      invoice_payload(
        id: "inv-101",
        contact_id: "c-58",
        number: "INV-101",
        balance: "250.00",
        total: "250.00",
        date: 10.days.ago.to_date.iso8601,
        due_date: 5.days.ago.to_date.iso8601,
        email: "billing@acme.com"
      )
    ])
    allow(xero_client).to receive(:query_contacts).and_return([
      { "ContactID" => "c-58", "Name" => "Acme Co", "EmailAddress" => "billing@acme.com" }
    ])

    result = described_class.execute(organization: organization, client: xero_client)

    expect(result).to be_success
    expect(result.data[:counts]).to eq(fetched: 1, created: 1, updated: 0, merged: 0)
    client_row = organization.clients.find_by!(external_id: "c-58")
    expect(client_row.name).to eq("Acme Co")
    expect(client_row.primary_email).to eq("billing@acme.com")
    expect(client_row.domain).to eq("acme.com")

    invoice = organization.invoices.find_by!(external_id: "inv-101")
    expect(invoice.invoice_number).to eq("INV-101")
    expect(invoice.books_status).to eq("open")
    expect(invoice.pay_link_token).to eq("https://in.xero.com/INV-101")
    expect(integration.reload.last_synced_at).to be_present
  end

  it "does not fetch contacts when there are no open invoices" do
    allow(xero_client).to receive(:query_open_invoices).and_return([])

    result = described_class.execute(organization: organization, client: xero_client)

    expect(result).to be_success
    expect(result.data[:counts][:fetched]).to eq(0)
    expect(integration.reload.last_synced_at).to be_present
  end
end
