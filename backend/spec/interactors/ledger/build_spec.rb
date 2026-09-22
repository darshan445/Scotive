# frozen_string_literal: true

require "rails_helper"

RSpec.describe Ledger::Build do
  include ActiveSupport::Testing::TimeHelpers

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "at",
      connection_status: "connected"
    )
  end
  let(:client_row) do
    organization.clients.create!(
      integration: qbo,
      external_id: "1",
      name: "Acme",
      primary_email: "ap@acme.com",
      domain: "acme.com",
      associated_emails: [ "ap@acme.com" ]
    )
  end

  it "serializes invoices for the dashboard" do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-1",
      invoice_number: "INV-1",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 120,
      balance_remaining: 120,
      current_ar_status: "broken_promise",
      active_promise_date: Date.new(2026, 9, 10)
    )

    result = described_class.execute(organization: organization)
    expect(result.success?).to eq(true)
    row = result.data[:invoices].first
    expect(row[:status]).to eq("promise_broken")
    expect(row[:counterparty_email]).to eq("ap@acme.com")
    expect(row[:invoice_ref]).to eq("INV-1")
    expect(row[:amount]).to eq(120.0)
    expect(row[:unmatched]).to eq(true)
    expect(result.data[:client_count]).to eq(1)
  end

  it "exposes unmatched when no thread is linked and maps leftover unmatched status to the clock" do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-2",
      invoice_number: "INV-2",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 80,
      balance_remaining: 80,
      current_ar_status: "unmatched"
    )

    travel_to Time.utc(2026, 9, 19, 12) do
      result = described_class.execute(organization: organization)
      row = result.data[:invoices].first
      expect(row[:status]).to eq("overdue")
      expect(row[:unmatched]).to eq(true)
      expect(row[:has_thread]).to eq(false)
    end
  end
end
