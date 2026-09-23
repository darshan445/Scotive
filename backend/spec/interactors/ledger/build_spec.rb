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
      chase_status: "needs_you",
      expected_pay_date: Date.new(2026, 9, 10)
    )

    result = described_class.execute(organization: organization)
    expect(result.success?).to eq(true)
    row = result.data[:invoices].first
    expect(row[:status]).to eq("needs_you")
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
      books_status: "open"
    )

    travel_to Time.utc(2026, 9, 19, 12) do
      result = described_class.execute(organization: organization)
      row = result.data[:invoices].first
      expect(row[:status]).to eq("watching")
      expect(row[:unmatched]).to eq(true)
      expect(row[:has_thread]).to eq(false)
    end
  end

  it "puts a Firm draft on Needs you with cadence labels" do
    invoice = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-3",
      invoice_number: "INV-3",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 4200,
      balance_remaining: 4200,
      chase_status: "watching"
    )
    invoice.outbox_messages.create!(
      organization: organization,
      status: "draft",
      cadence_step: "firm_plus_7",
      to_address: "ap@acme.com",
      subject: "Invoice INV-3",
      body: "Firm draft",
      scheduled_send_at: Time.utc(2026, 9, 8, 10, 15)
    )

    result = described_class.execute(organization: organization)
    row = result.data[:invoices].find { |item| item[:invoice_ref] == "INV-3" }
    expect(row[:status]).to eq("needs_you")
    expect(row[:reason]).to eq("firm_ready")
    expect(row[:pending_step]).to eq("firm_plus_7")
    expect(row[:pending_step_label]).to eq("Firm")
    expect(row[:cadence][:title]).to match(/Firm reminder/)
    expect(row[:pending_subject]).to eq("Invoice INV-3")
    expect(row[:pending_body]).to eq("Firm draft")
    expect(row[:last_sent_at]).to be_nil
    expect(row[:last_sent_label]).to be_nil
  end

  it "exposes the last Friendly send so Needs you can show latest activity" do
    invoice = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-4",
      invoice_number: "INV-4",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 5600,
      balance_remaining: 5600,
      chase_status: "watching"
    )
    sent_at = Time.utc(2026, 9, 18, 10, 15)
    invoice.outbox_messages.create!(
      organization: organization,
      status: "sent",
      cadence_step: "nudge_plus_3",
      to_address: "ap@acme.com",
      subject: "Invoice INV-4",
      body: "Friendly 3",
      scheduled_send_at: sent_at,
      sent_at: sent_at
    )
    invoice.outbox_messages.create!(
      organization: organization,
      status: "draft",
      cadence_step: "firm_plus_7",
      to_address: "ap@acme.com",
      subject: "Invoice INV-4",
      body: "Firm draft",
      scheduled_send_at: Time.utc(2026, 9, 23, 10, 15)
    )

    result = described_class.execute(organization: organization)
    row = result.data[:invoices].find { |item| item[:invoice_ref] == "INV-4" }
    expect(row[:reason]).to eq("firm_ready")
    expect(row[:last_sent_label]).to eq("Friendly 3")
    expect(row[:last_sent_at]).to eq(sent_at.iso8601)
  end

  it "exposes when the user stopped chasing" do
    invoice = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-5",
      invoice_number: "INV-5",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 2500,
      balance_remaining: 2500,
      chase_status: "stopped"
    )
    stopped_at = Time.utc(2026, 9, 18, 10, 0)
    invoice.invoice_chase_events.create!(event_type: "stopped", actor: "user", created_at: stopped_at)

    result = described_class.execute(organization: organization)
    row = result.data[:invoices].find { |item| item[:invoice_ref] == "INV-5" }
    expect(row[:status]).to eq("stopped")
    expect(row[:stopped_at]).to eq(stopped_at.iso8601)
  end
end
