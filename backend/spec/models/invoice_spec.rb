# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoice do
  include ActiveSupport::Testing::TimeHelpers

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:qbo) do
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

  def build_invoice(due_date:, chase: "watching", inbound_at: nil, wait: nil)
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: SecureRandom.uuid,
      invoice_number: "INV-#{SecureRandom.hex(3)}",
      issue_date: Date.new(2026, 8, 1),
      due_date: due_date,
      total_amount: 100,
      balance_remaining: 100,
      books_status: "open",
      chase_status: chase,
      last_human_inbound_at: inbound_at,
      expected_pay_date: wait
    )
  end

  around do |example|
    travel_to(Time.utc(2026, 9, 18, 12)) { example.run }
  end

  it "keeps silent invoices inside the Friendly window on Auto reminders" do
    future = build_invoice(due_date: Date.new(2026, 9, 22))
    due_today = build_invoice(due_date: Date.new(2026, 9, 18))
    day_seven = build_invoice(due_date: Date.new(2026, 9, 11))

    expect(future.list_bucket).to eq("auto_reminders")
    expect(future.cadence_allowed?).to eq(true)
    expect(due_today.list_bucket).to eq("auto_reminders")
    expect(day_seven.list_bucket).to eq("auto_reminders")
    expect(day_seven.past_friendly_window?).to eq(false)
  end

  it "moves a silent invoice past day 7 to Needs you without allowing Friendly" do
    late = build_invoice(due_date: Date.new(2026, 9, 10))

    expect(late.days_late).to eq(8)
    expect(late.past_friendly_window?).to eq(true)
    expect(late.list_bucket).to eq("needs_you")
    expect(late.cadence_allowed?).to eq(false)
  end

  it "uses the last enabled Friendly slot as the Watching window" do
    organization.update!(
      escalation_offsets: {
        "before_due" => { "enabled" => true, "days" => 3 },
        "on_due" => { "enabled" => true },
        "overdue" => { "enabled" => false, "days" => 7 }
      }
    )
    late = build_invoice(due_date: Date.new(2026, 9, 16))

    expect(Cadence::Steps.last_friendly_offset(organization)).to eq(0)
    expect(late.days_late).to eq(2)
    expect(late.past_friendly_window?).to eq(true)
    expect(late.list_bucket).to eq("needs_you")
  end

  it "puts a reply on Needs you even when still inside 7 days" do
    replied = build_invoice(due_date: Date.new(2026, 9, 20), inbound_at: Time.utc(2026, 9, 16, 9))

    expect(replied.list_bucket).to eq("needs_you")
    expect(replied.cadence_allowed?).to eq(false)
  end

  it "leaves a future check-back on Watching" do
    sleeping = build_invoice(due_date: Date.new(2026, 9, 1), wait: Date.new(2026, 9, 25))

    expect(sleeping.sleeping?).to eq(true)
    expect(sleeping.list_bucket).to eq("watching")
  end

  it "does not override Stopped or Paid" do
    stopped = build_invoice(due_date: Date.new(2026, 9, 1), chase: "stopped")
    paid = build_invoice(due_date: Date.new(2026, 9, 1))
    paid.update!(books_status: "paid", balance_remaining: 0)

    expect(stopped.list_bucket).to eq("stopped")
    expect(paid.list_bucket).to eq("paid")
  end
end
