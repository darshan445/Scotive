# frozen_string_literal: true

# Invoices::ApplyAction Interactor
# Purpose: deterministic user actions (no LLM) — paid, undo, pause, deny claim, due date.
# Methods:
# - execute

class Invoices::ApplyAction
  include ExecuteMethodHelper
  include LogHelper

  ACTIONS = %w[
    mark_paid undo pause resume deny_payment_claim resolve_dispute set_due_date skip_due_date skip_followup
  ].freeze
  PAUSE_UNTIL = Time.utc(9999, 1, 1)
  BOOKS_TRIGGERS = %w[books_sync books_webhook].freeze

  def self.execute(organization:, invoice_id:, action:, due_date: nil)
    new(organization: organization, invoice_id: invoice_id, action: action, due_date: due_date).execute
  end

  def initialize(organization:, invoice_id:, action:, due_date:)
    @organization = organization
    @invoice_id = invoice_id
    @action = action.to_s
    @due_date = due_date
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?
      raise_string_error("Unknown action") unless ACTIONS.include?(action)

      invoice = nil
      Invoice.transaction do
        invoice = organization.invoices.lock.find_by(id: invoice_id)
        raise_string_error("Invoice not found") if invoice.blank?

        case action
        when "mark_paid" then mark_paid!(invoice)
        when "undo" then undo!(invoice)
        when "pause" then pause!(invoice)
        when "resume" then resume!(invoice)
        when "deny_payment_claim" then deny_payment_claim!(invoice)
        when "resolve_dispute" then resolve_dispute!(invoice)
        when "set_due_date" then set_due_date!(invoice)
        when "skip_due_date" then invoice
        when "skip_followup" then skip_followup!(invoice)
        end
      end

      {
        action: action,
        status: invoice.current_ar_status,
        invoice: Ledger::InvoicePayload.for(invoice.reload)
      }
    end
  end

  private

  attr_reader :organization, :invoice_id, :action, :due_date

  def mark_paid!(invoice)
    if invoice.current_ar_status != "paid"
      apply_transition!(
        invoice,
        to: "paid",
        needs_reply: false,
        promise_date: nil,
        disputed_amount: nil
      )
    end
    OutboxMessage.cancel_pending_for!(invoice, "paid_in_books")
  end

  def undo!(invoice)
    last = latest_active_transition(invoice)
    raise_string_error("Nothing to undo") if last.blank?
    raise_string_error("Books state cannot be undone") if BOOKS_TRIGGERS.include?(last.trigger_source)

    last.update!(is_reverted: true)
    previous = latest_active_transition(invoice.reload)
    if previous
      invoice.update!(
        current_ar_status: previous.to_status,
        needs_reply: previous.needs_reply,
        active_promise_date: previous.promise_date,
        disputed_claim_amount: previous.disputed_amount
      )
    else
      invoice.update!(
        current_ar_status: clock_status(invoice),
        needs_reply: false,
        active_promise_date: nil,
        disputed_claim_amount: nil
      )
    end
  end

  def pause!(invoice)
    invoice.update!(snoozed_until: PAUSE_UNTIL)
    invoice.outbox_messages.where(status: "scheduled").find_each do |row|
      row.update!(status: "cancelled", cancellation_reason: "invoice_snoozed_by_user")
    end
  end

  def resume!(invoice)
    invoice.update!(snoozed_until: nil)
  end

  def deny_payment_claim!(invoice)
    raise_string_error("No payment claim to deny") unless invoice.current_ar_status == "paid_unconfirmed"

    promise = unexpired_promise(invoice)
    if promise
      apply_transition!(
        invoice,
        to: "promised",
        needs_reply: false,
        promise_date: promise,
        disputed_amount: nil
      )
    else
      apply_transition!(
        invoice,
        to: clock_status(invoice),
        needs_reply: false,
        promise_date: nil,
        disputed_amount: nil
      )
    end
  end

  def resolve_dispute!(invoice)
    raise_string_error("Invoice is not disputed") unless invoice.current_ar_status == "disputed"

    apply_transition!(
      invoice,
      to: clock_status(invoice),
      needs_reply: false,
      promise_date: nil,
      disputed_amount: nil
    )
  end

  def skip_followup!(invoice)
    invoice.outbox_messages.where(status: "draft").find_each do |row|
      row.update!(status: "cancelled", cancellation_reason: "skipped_by_user")
    end
  end

  def set_due_date!(invoice)
    parsed = parse_date(due_date)
    raise_string_error("Due date is required") if parsed.blank?

    invoice.update!(due_date: parsed)
    if %w[invoiced overdue].include?(invoice.current_ar_status)
      next_status = clock_status(invoice)
      if next_status != invoice.current_ar_status
        apply_transition!(
          invoice,
          to: next_status,
          needs_reply: invoice.needs_reply,
          promise_date: invoice.active_promise_date,
          disputed_amount: invoice.disputed_claim_amount
        )
      end
    end
  end

  def apply_transition!(invoice, to:, needs_reply:, promise_date:, disputed_amount:)
    previous = invoice.current_ar_status
    invoice.update!(
      current_ar_status: to,
      needs_reply: needs_reply,
      active_promise_date: promise_date,
      disputed_claim_amount: disputed_amount
    )
    invoice.invoice_state_transitions.create!(
      from_status: previous,
      to_status: to,
      trigger_source: "manual_user",
      promise_date: promise_date,
      disputed_amount: disputed_amount,
      needs_reply: needs_reply,
      created_at: Time.current
    )
  end

  def latest_active_transition(invoice)
    rows = invoice.invoice_state_transitions.where(is_reverted: false).order(created_at: :desc, id: :desc).to_a
    rows.find { |row| row.to_status == invoice.current_ar_status } || rows.first
  end

  def unexpired_promise(invoice)
    date = invoice.invoice_state_transitions
      .where(is_reverted: false, to_status: "promised")
      .where("promise_date >= ?", Date.current)
      .order(created_at: :desc)
      .limit(1)
      .pick(:promise_date)
    date || (invoice.active_promise_date if invoice.active_promise_date.present? && invoice.active_promise_date >= Date.current)
  end

  def clock_status(invoice)
    invoice.due_date < Date.current ? "overdue" : "invoiced"
  end

  def parse_date(value)
    return if value.blank?
    return value if value.respond_to?(:to_date) && !value.is_a?(String)

    Date.parse(value.to_s)
  rescue Date::Error, ArgumentError
    nil
  end
end
