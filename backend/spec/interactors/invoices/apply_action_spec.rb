# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoices::ApplyAction do
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
      primary_email: "ap@acme.com",
      domain: "acme.com"
    )
  end
  let(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-12",
      invoice_number: "INV-12",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 250,
      balance_remaining: 250,
      chase_status: "needs_you"
    )
  end

  def execute!(action, **extra)
    described_class.execute(organization: organization, invoice_id: invoice.id, action: action, **extra)
  end

  it "waits until a date, resumes, and stops chasing" do
    travel_to Time.utc(2026, 9, 18, 12) do
      waited = execute!("wait_until", wait_until: "2026-09-19")
      expect(waited.success?).to eq(true)
      expect(invoice.reload.chase_status).to eq("watching")
      expect(invoice.expected_pay_date).to eq(Date.new(2026, 9, 19))
      expect(invoice.list_bucket).to eq("watching")

      execute!("resume")
      expect(invoice.reload.expected_pay_date).to be_nil
      expect(invoice.chase_status).to eq("needs_you")

      invoice.update!(chase_status: "needs_you")
      execute!("stop_chasing")
      expect(invoice.reload.chase_status).to eq("stopped")
      expect(invoice.list_bucket).to eq("stopped")

      restarted = execute!("wait_until", wait_until: "2026-09-25")
      expect(restarted.success?).to eq(true)
      expect(invoice.reload.chase_status).to eq("watching")
      expect(invoice.expected_pay_date).to eq(Date.new(2026, 9, 25))
      expect(invoice.list_bucket).to eq("watching")
    end
  end

  it "marks paid from the ledger action and cancels outbox" do
    invoice.outbox_messages.create!(
      organization: organization,
      status: "scheduled",
      cadence_step: "nudge_plus_3",
      to_address: "ap@acme.com",
      subject: "Re: INV-12",
      body: "Checking in",
      scheduled_send_at: Time.current
    )

    paid = execute!("mark_paid")
    expect(paid.success?).to eq(true)
    expect(invoice.reload.books_status).to eq("paid")
    expect(invoice.list_bucket).to eq("paid")
    expect(invoice.outbox_messages.sole.status).to eq("cancelled")
  end

  it "sets a due date and skips draft follow-ups" do
    invoice.outbox_messages.create!(
      organization: organization,
      status: "draft",
      cadence_step: "firm_plus_7",
      to_address: "ap@acme.com",
      subject: "Re: INV-12",
      body: "Firm copy",
      scheduled_send_at: Time.current
    )
    moved = execute!("set_due_date", due_date: "2026-09-30")
    expect(moved.success?).to eq(true)
    expect(invoice.reload.due_date).to eq(Date.new(2026, 9, 30))

    result = execute!("skip_followup")
    expect(result.success?).to eq(true)
    expect(invoice.outbox_messages.sole.status).to eq("cancelled")
  end
end
