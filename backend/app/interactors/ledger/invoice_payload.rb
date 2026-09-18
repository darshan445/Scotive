# frozen_string_literal: true

# Ledger JSON for dashboard, clients, and invoice drawers.
module Ledger::InvoicePayload
  UI_STATUS = {
    "broken_promise" => "promise_broken",
    "voided" => "written_off",
    "unmatched" => "invoiced"
  }.freeze

  module_function

  def for(invoice)
    client = invoice.client
    primary = primary_conversation(invoice)
    paid_at = paid_at_for(invoice)
    {
      _id: invoice.id,
      status: ui_status(invoice.current_ar_status),
      amount: invoice.total_amount.to_f,
      balance_remaining: invoice.balance_remaining.to_f,
      paid_amount: (invoice.total_amount.to_d - invoice.balance_remaining.to_d).to_f,
      currency: invoice.currency,
      invoice_ref: invoice.invoice_number,
      source_subject: primary&.subject,
      source_date: iso_date(invoice.issue_date),
      source_thread_id: primary&.external_thread_id,
      due_date: iso_date(invoice.due_date),
      promise_date: iso_date(invoice.active_promise_date),
      payment_claim_pending: invoice.current_ar_status == "paid_unconfirmed",
      tracking_paused: paused?(invoice),
      counterparty_name: client&.name,
      counterparty_email: client&.primary_email,
      client_identity_key: client&.id,
      needs_reply: invoice.needs_reply,
      disputed_claim_amount: invoice.disputed_claim_amount&.to_f,
      created_at: invoice.created_at&.iso8601,
      status_updated_at: invoice.updated_at&.iso8601,
      paid_at: paid_at&.iso8601,
      paid_via: paid_via_for(invoice),
      snoozed_until: invoice.snoozed_until&.iso8601
    }
  end

  def ui_status(status)
    UI_STATUS.fetch(status.to_s, status.to_s)
  end

  def primary_conversation(invoice)
    links = invoice.invoice_conversations.to_a
    primary = links.find(&:is_primary)
    (primary || links.first)&.conversation
  end

  def paused?(invoice)
    invoice.snoozed_until.present? && invoice.snoozed_until > Time.current
  end

  def paid_at_for(invoice)
    return unless invoice.current_ar_status == "paid"

    paid_transition(invoice)&.created_at || invoice.updated_at
  end

  def paid_via_for(invoice)
    return unless invoice.current_ar_status == "paid"

    paid_transition(invoice)&.trigger_source.to_s.start_with?("books") ? "quickbooks" : "manual"
  end

  def paid_transition(invoice)
    invoice.invoice_state_transitions.select { |row| row.to_status == "paid" }
      .max_by(&:created_at)
  end

  def iso_date(value)
    value&.to_date&.iso8601
  end
end
