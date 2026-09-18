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

  def create_invoice!(status:, number:, due_date: Date.new(2026, 9, 1), needs_reply: false, promise_date: nil)
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: number,
      invoice_number: number,
      issue_date: Date.new(2026, 8, 1),
      due_date: due_date,
      total_amount: 100,
      balance_remaining: 100,
      current_ar_status: status,
      needs_reply: needs_reply,
      active_promise_date: promise_date
    )
  end

  it "groups overdue, broken promise, says-paid, and needs-reply invoices" do
    travel_to Time.utc(2026, 9, 18, 12) do
      overdue = create_invoice!(status: "overdue", number: "INV-OD")
      broken = create_invoice!(status: "broken_promise", number: "INV-BP", promise_date: Date.new(2026, 9, 10))
      claimed = create_invoice!(status: "paid_unconfirmed", number: "INV-PU")
      reply = create_invoice!(status: "invoiced", number: "INV-NR", due_date: Date.new(2026, 9, 30), needs_reply: true)
      create_invoice!(status: "invoiced", number: "INV-OK", due_date: Date.new(2026, 9, 30))

      result = described_class.execute(organization: organization)
      expect(result.success?).to eq(true)
      expect(result.data[:due_overdue].map { |row| row[:_id] }).to eq([ overdue.id ])
      expect(result.data[:broken_promises].map { |row| row[:_id] }).to eq([ broken.id ])
      expect(result.data[:confirm_prompts].map { |row| row[:_id] }).to eq([ claimed.id ])
      expect(result.data[:needs_reply].map { |row| row[:_id] }).to eq([ reply.id ])
      expect(result.data[:stale_prompts]).to eq([])
    end
  end
end
