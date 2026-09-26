# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::MailTemplate do
  let(:organization) { Organization.create!(name: "Studio") }
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      connection_status: "connected"
    )
  end
  let(:client_row) do
    organization.clients.create!(
      integration: qbo,
      external_id: "1",
      name: "Acme",
      primary_email: "ap@acme.com"
    )
  end
  let(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-12",
      invoice_number: "INV-12",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 4),
      total_amount: 250,
      balance_remaining: 250,
      pay_link_token: "https://pay.qbo.test/inv-12"
    )
  end

  it "wraps prose in a summary box and a View and pay button" do
    mail = described_class.for(
      invoice,
      prose: "Hi Acme,\n\nChecking on INV-12.\n\nThanks",
      include_pay_link: true
    )

    expect(mail[:html]).to include("Checking on INV-12.")
    expect(mail[:html]).to include("Invoice summary")
    expect(mail[:html]).to include("View and pay this invoice")
    expect(mail[:html]).to include("https://pay.qbo.test/inv-12")
    expect(mail[:html]).not_to include("Pay invoice INV-12")
    expect(mail[:text]).to include("View and pay this invoice: https://pay.qbo.test/inv-12")
  end

  it "omits the pay button when asked" do
    mail = described_class.for(invoice, prose: "The balance stands.", include_pay_link: false)
    expect(mail[:html]).not_to include("View and pay this invoice")
    expect(mail[:html]).to include("Invoice summary")
  end
end
