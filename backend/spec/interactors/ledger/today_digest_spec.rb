# frozen_string_literal: true

require "rails_helper"

RSpec.describe Ledger::TodayDigest do
  include ActiveSupport::Testing::TimeHelpers

  let(:organization) { Organization.create!(name: "Ada's workspace") }
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

  def create_invoice!(number:, chase: "watching", wait: nil)
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: number,
      invoice_number: number,
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 30),
      total_amount: 100,
      balance_remaining: 100,
      chase_status: chase,
      expected_pay_date: wait
    )
  end

  it "returns only Needs you invoices" do
    travel_to Time.utc(2026, 9, 18, 12) do
      reply = create_invoice!(number: "INV-NR", chase: "needs_you")
      create_invoice!(number: "INV-OK")
      create_invoice!(number: "INV-WAIT", wait: Date.new(2026, 9, 20))

      result = described_class.execute(organization: organization)
      expect(result.success?).to eq(true)
      expect(result.data[:needs_you].map { |row| row[:_id] }).to eq([ reply.id ])
    end
  end
end
