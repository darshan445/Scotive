# frozen_string_literal: true

require "rails_helper"

RSpec.describe Sync::ApplyClock do
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
  let(:qbo_client) { instance_double(Quickbooks::QuickbookClient) }

  def create_invoice!(chase:, due_date:, wait: nil, balance: 100, external_id: nil, books: "open")
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: external_id || SecureRandom.uuid,
      invoice_number: "INV-#{SecureRandom.hex(3)}",
      issue_date: Date.new(2026, 8, 1),
      due_date: due_date,
      total_amount: 100,
      balance_remaining: balance,
      books_status: books,
      chase_status: chase,
      expected_pay_date: wait
    )
  end

  def qbo_payload(id:, balance:)
    {
      "Id" => id,
      "DocNumber" => "INV-#{id}",
      "TxnDate" => "2026-08-01",
      "DueDate" => "2026-09-30",
      "TotalAmt" => 100,
      "Balance" => balance,
      "CustomerRef" => { "value" => "1", "name" => "Acme" }
    }
  end

  it "moves an expired wait back to Needs you and leaves a future wait in Watching" do
    travel_to Time.utc(2026, 9, 18, 12) do
      expired = create_invoice!(chase: "watching", due_date: Date.new(2026, 9, 30), wait: Date.new(2026, 9, 17))
      waiting = create_invoice!(chase: "watching", due_date: Date.new(2026, 9, 30), wait: Date.new(2026, 9, 20))
      open_row = create_invoice!(chase: "watching", due_date: Date.new(2026, 9, 30))

      result = described_class.execute(organization: organization, client: qbo_client)
      expect(result.success?).to eq(true)
      expect(result.data[:wait_expired]).to eq(1)
      expect(expired.reload.chase_status).to eq("needs_you")
      expect(expired.invoice_chase_events.last.event_type).to eq("wait_expired")
      expect(waiting.reload.chase_status).to eq("watching")
      expect(open_row.reload.chase_status).to eq("watching")
    end
  end

  it "asks QuickBooks before flipping and stays Paid when the balance is zero" do
    qbo.update!(access_token: "at", refresh_token: "rt", token_expires_at: 1.hour.from_now)
    travel_to Time.utc(2026, 9, 18, 12) do
      paid = create_invoice!(
        chase: "watching",
        due_date: Date.new(2026, 9, 30),
        wait: Date.new(2026, 9, 17),
        external_id: "95"
      )
      unpaid = create_invoice!(
        chase: "watching",
        due_date: Date.new(2026, 9, 30),
        wait: Date.new(2026, 9, 17),
        external_id: "96"
      )
      allow(qbo_client).to receive(:get_invoice).with(hash_including(id: "95")).and_return(qbo_payload(id: "95", balance: 0))
      allow(qbo_client).to receive(:get_invoice).with(hash_including(id: "96")).and_return(qbo_payload(id: "96", balance: 100))

      result = described_class.execute(organization: organization, client: qbo_client)
      expect(result.success?).to eq(true)
      expect(result.data[:wait_expired]).to eq(1)
      expect(paid.reload.books_status).to eq("paid")
      expect(paid.chase_status).to eq("watching")
      expect(paid.list_bucket).to eq("paid")
      expect(unpaid.reload.chase_status).to eq("needs_you")
      expect(unpaid.books_status).to eq("open")
    end
  end

  it "moves a silent invoice off Watching when Friendly is over" do
    travel_to Time.utc(2026, 9, 18, 12) do
      late = create_invoice!(chase: "watching", due_date: Date.new(2026, 9, 10))
      still_window = create_invoice!(chase: "watching", due_date: Date.new(2026, 9, 11))

      result = described_class.execute(organization: organization, client: qbo_client)
      expect(result.success?).to eq(true)
      expect(result.data[:friendly_ended]).to eq(1)
      expect(late.reload.chase_status).to eq("needs_you")
      expect(late.invoice_chase_events.last.event_type).to eq("friendly_window_ended")
      expect(still_window.reload.chase_status).to eq("watching")
    end
  end

  it "does not flip when QuickBooks cannot be reached" do
    qbo.update!(access_token: "at", refresh_token: "rt", token_expires_at: 1.hour.from_now)
    travel_to Time.utc(2026, 9, 18, 12) do
      row = create_invoice!(
        chase: "watching",
        due_date: Date.new(2026, 9, 30),
        wait: Date.new(2026, 9, 17),
        external_id: "97"
      )
      allow(qbo_client).to receive(:get_invoice).and_raise(Faraday::TimeoutError.new("timeout"))

      result = described_class.execute(organization: organization, client: qbo_client)
      expect(result.success?).to eq(true)
      expect(result.data[:wait_expired]).to eq(0)
      expect(row.reload.chase_status).to eq("watching")
    end
  end
end
