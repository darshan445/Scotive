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
      current_ar_status: "overdue"
    )
  end

  def execute!(action, **extra)
    described_class.execute(organization: organization, invoice_id: invoice.id, action: action, **extra)
  end

  it "marks paid, cancels pending outbox, and undoes back to the prior ledger row" do
    travel_to Time.utc(2026, 9, 18, 12) do
      invoice.invoice_state_transitions.create!(
        from_status: "invoiced",
        to_status: "overdue",
        trigger_source: "clock_cron",
        created_at: Time.current
      )
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
      expect(invoice.reload.current_ar_status).to eq("paid")
      expect(invoice.needs_reply).to eq(false)
      expect(invoice.outbox_messages.sole.status).to eq("cancelled")
      expect(paid.data[:invoice][:paid_via]).to eq("manual")

      undone = execute!("undo")
      expect(undone.success?).to eq(true)
      expect(invoice.reload.current_ar_status).to eq("overdue")
      expect(invoice.invoice_state_transitions.find_by!(to_status: "paid").is_reverted).to eq(true)
    end
  end

  it "pauses cadence, resumes tracking, and denies a payment claim via the fallback matrix" do
    travel_to Time.utc(2026, 9, 18, 12) do
      execute!("pause")
      expect(invoice.reload.snoozed_until).to be > Time.current
      execute!("resume")
      expect(invoice.reload.snoozed_until).to be_nil

      invoice.update!(current_ar_status: "paid_unconfirmed", active_promise_date: Date.new(2026, 9, 20))
      invoice.invoice_state_transitions.create!(
        from_status: "overdue",
        to_status: "promised",
        trigger_source: "ai_reader",
        promise_date: Date.new(2026, 9, 20),
        created_at: 2.days.ago
      )
      invoice.invoice_state_transitions.create!(
        from_status: "promised",
        to_status: "paid_unconfirmed",
        trigger_source: "ai_reader",
        created_at: 1.day.ago
      )
      denied = execute!("deny_payment_claim")
      expect(denied.success?).to eq(true)
      expect(invoice.reload.current_ar_status).to eq("promised")
      expect(invoice.active_promise_date).to eq(Date.new(2026, 9, 20))
    end
  end

  it "resolves a dispute to clock status and does not restore a promise" do
    travel_to Time.utc(2026, 9, 18, 12) do
      invoice.update!(current_ar_status: "disputed", active_promise_date: Date.new(2026, 9, 30), disputed_claim_amount: 50)
      result = execute!("resolve_dispute")
      expect(result.success?).to eq(true)
      expect(invoice.reload.current_ar_status).to eq("overdue")
      expect(invoice.active_promise_date).to be_nil
      expect(invoice.disputed_claim_amount).to be_nil
    end
  end

  it "sets a due date and refuses to undo a books paid row" do
    travel_to Time.utc(2026, 9, 18, 12) do
      moved = execute!("set_due_date", due_date: "2026-09-30")
      expect(moved.success?).to eq(true)
      expect(invoice.reload.due_date).to eq(Date.new(2026, 9, 30))
      expect(invoice.current_ar_status).to eq("invoiced")

      invoice.update!(current_ar_status: "paid")
      invoice.invoice_state_transitions.create!(
        from_status: "overdue",
        to_status: "paid",
        trigger_source: "books_webhook",
        created_at: Time.current
      )
      expect(execute!("undo").errors).to match(/Books state/)
    end
  end

  it "cancels draft follow-ups when the user skips" do
    invoice.outbox_messages.create!(
      organization: organization,
      status: "draft",
      cadence_step: "firm_plus_7",
      to_address: "ap@acme.com",
      subject: "Re: INV-12",
      body: "Firm copy",
      scheduled_send_at: Time.current
    )
    result = execute!("skip_followup")
    expect(result.success?).to eq(true)
    expect(invoice.outbox_messages.sole.status).to eq("cancelled")
    expect(invoice.outbox_messages.sole.cancellation_reason).to eq("skipped_by_user")
  end
end
