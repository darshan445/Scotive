# frozen_string_literal: true

# Persist chase / books events. No LLM. Status only from inbound, user clicks, or the ledger.
module Invoices::ChaseWrite
  def record_chase_event!(invoice, type:, actor: "system", message: nil, quote: nil, expected_pay_date: nil)
    invoice.invoice_chase_events.create!(
      event_type: type,
      actor: actor,
      message: message,
      quote: quote.to_s.presence,
      expected_pay_date: expected_pay_date,
      created_at: Time.current
    )
  end

  def apply_human_inbound!(invoice, message)
    return if invoice.books_closed?

    quote = message.clean_body.to_s.strip.truncate(240)
    attrs = {
      last_human_inbound_at: message.sent_at,
      last_human_inbound_message_id: message.id
    }
    unless invoice.chase_status == "stopped"
      attrs[:chase_status] = "needs_you"
      attrs[:expected_pay_date] = nil
      OutboxMessage.cancel_pending_for!(invoice, "chase_paused")
    end
    invoice.update!(attrs)
    record_chase_event!(invoice, type: "human_inbound", message: message, quote: quote)
  end

  def apply_wait_until!(invoice, date, actor: "user", quote: nil)
    invoice.update!(chase_status: "watching", expected_pay_date: date)
    OutboxMessage.cancel_pending_for!(invoice, "waiting_until_date")
    record_chase_event!(invoice, type: "wait_set", actor: actor, quote: quote, expected_pay_date: date)
  end

  def apply_resume!(invoice)
    invoice.update!(chase_status: "needs_you", expected_pay_date: nil)
    OutboxMessage.cancel_pending_for!(invoice, "resumed")
    record_chase_event!(invoice, type: "resumed", actor: "user")
  end

  # Silent invoices leave Watching when Friendly is over (today > due + last Friendly offset).
  def apply_friendly_window!(invoice)
    return if invoice.books_closed?
    return if invoice.chase_status == "stopped"
    return if invoice.sleeping?
    return if invoice.last_human_inbound_at.present?
    return unless invoice.past_friendly_window?
    return if invoice.chase_status == "needs_you"

    invoice.update!(chase_status: "needs_you")
    record_chase_event!(invoice, type: "friendly_window_ended")
    escalate_draft!(invoice)
  end

  def escalate_draft!(invoice)
    return if invoice.outbox_messages.where(status: "sent", cadence_step: Cadence::Steps::FIRM).exists?

    Cadence::Enqueue.execute(invoice: invoice, step: Cadence::Steps::FIRM)
  end

  def apply_stop!(invoice)
    invoice.update!(chase_status: "stopped")
    OutboxMessage.cancel_pending_for!(invoice, "stopped_by_user")
    record_chase_event!(invoice, type: "stopped", actor: "user")
  end

  def apply_wait_expired!(invoice)
    return if invoice.books_closed?
    return unless invoice.chase_status == "watching"
    return unless invoice.wait_expired?

    invoice.update!(chase_status: "needs_you")
    record_chase_event!(invoice, type: "wait_expired", expected_pay_date: invoice.expected_pay_date)
  end

  def apply_books_status!(invoice, status)
    previous = invoice.books_status
    invoice.books_status = status
    if Invoice::CLOSED_BOOKS.include?(status)
      invoice.expected_pay_date = nil
      OutboxMessage.cancel_pending_for!(invoice, status == "voided" ? "invoice_voided" : "paid_in_books")
    end
    invoice.save!
    return if previous == status || status == "open"

    type = { "paid" => "books_paid", "voided" => "books_voided", "partial" => "books_partial" }[status]
    record_chase_event!(invoice, type: type) if type
  end
end
