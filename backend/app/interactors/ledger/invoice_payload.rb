# frozen_string_literal: true

# Ledger JSON for dashboard, clients, and invoice drawers.
module Ledger::InvoicePayload
  module_function

  STEP_LABELS = {
    "notice_minus_3" => "Before due",
    "due_today" => "Due day",
    "nudge_plus_3" => "After due",
    "firm_plus_7" => "Firm",
    "urgent_plus_14" => "Final",
    "broken_promise" => "Wait expired"
  }.freeze

  def for(invoice)
    client = invoice.client
    primary = primary_conversation(invoice)
    event = latest_event(invoice)
    paid_at = paid_at_for(invoice)
    suggested = suggested_wait_for(invoice)
    pending = pending_outbox(invoice)
    sent = last_sent_outbox(invoice)
    chase_send = last_chase_send(invoice, sent)
    {
      _id: invoice.id,
      status: invoice.list_bucket,
      books_status: invoice.books_status,
      chase_status: invoice.chase_status,
      unmatched: unmatched?(invoice),
      has_thread: !unmatched?(invoice),
      amount: invoice.total_amount.to_f,
      balance_remaining: invoice.balance_remaining.to_f,
      paid_amount: (invoice.total_amount.to_d - invoice.balance_remaining.to_d).to_f,
      currency: invoice.currency,
      invoice_ref: invoice.invoice_number,
      source_subject: primary&.subject,
      source_date: iso_date(invoice.issue_date),
      source_thread_id: primary&.external_thread_id,
      due_date: iso_date(invoice.due_date),
      days_late: days_late(invoice),
      last_friendly_offset: Cadence::Steps.last_friendly_offset(invoice.organization),
      expected_pay_date: iso_date(invoice.expected_pay_date),
      promise_date: iso_date(invoice.expected_pay_date),
      payment_claim_pending: false,
      tracking_paused: invoice.chase_status == "stopped",
      stopped_at: stopped_at_for(invoice),
      counterparty_name: client&.name,
      counterparty_email: client&.primary_email,
      client_identity_key: client&.id,
      needs_reply: invoice.list_bucket == "needs_you",
      last_human_inbound_at: invoice.last_human_inbound_at&.iso8601,
      last_human_inbound_quote: inbound_quote(invoice, event),
      reason: reason_for(invoice, event, pending),
      reason_quote: inbound_quote(invoice, event),
      suggested_wait_date: iso_date(suggested&.fetch(:date, nil)),
      suggested_wait_quote: suggested&.fetch(:quote, nil),
      pending_step: pending&.cadence_step,
      pending_step_label: STEP_LABELS[pending&.cadence_step],
      pending_outbox_status: pending&.status,
      pending_subject: pending&.subject,
      pending_body: pending&.body,
      next_send_at: pending&.scheduled_send_at&.iso8601,
      last_sent_at: chase_send&.fetch(:at, nil)&.iso8601,
      last_sent_label: chase_send&.fetch(:label, nil),
      cadence: cadence_for(invoice, pending),
      chase_result: chase_result_for(invoice, sent),
      created_at: invoice.created_at&.iso8601,
      status_updated_at: invoice.updated_at&.iso8601,
      paid_at: paid_at&.iso8601,
      paid_via: paid_via_for(invoice, event),
      snoozed_until: nil
    }
  end

  def unmatched?(invoice)
    return false if invoice.books_closed?

    invoice.invoice_conversations.empty?
  end

  def primary_conversation(invoice)
    links = invoice.invoice_conversations.to_a
    primary = links.find(&:is_primary)
    (primary || links.first)&.conversation
  end

  def paused?(invoice)
    invoice.list_bucket == "needs_you" || invoice.chase_status == "stopped" || invoice.sleeping?
  end

  def latest_event(invoice)
    invoice.invoice_chase_events.max_by(&:created_at)
  end

  def inbound_quote(invoice, event)
    return event.quote if event&.event_type == "human_inbound" && event.quote.present?

    invoice.last_human_inbound_message&.clean_body.to_s.strip.truncate(220).presence
  end

  def reason_for(invoice, event, pending = nil)
    if invoice.books_closed?
      invoice.books_status == "voided" ? "voided" : "paid"
    elsif invoice.chase_status == "stopped"
      "stopped"
    elsif invoice.chase_status == "needs_you" && invoice.wait_expired?
      "wait_date_passed"
    elsif pending&.status == "draft" && Cadence::Steps.draft?(pending.cadence_step)
      pending.cadence_step == "urgent_plus_14" ? "final_ready" : "firm_ready"
    elsif invoice.sleeping?
      "waiting_until"
    elsif event&.event_type == "human_inbound"
      "replied"
    elsif invoice.list_bucket == "needs_you"
      "needs_you"
    else
      "watching"
    end
  end

  def pending_outbox(invoice)
    invoice.outbox_messages.select { |row| %w[draft scheduled].include?(row.status) }.max_by(&:created_at)
  end

  def last_sent_outbox(invoice)
    invoice.outbox_messages.select { |row| row.status == "sent" }.max_by { |row| row.sent_at || row.created_at }
  end

  def last_outbound_message(invoice)
    invoice.invoice_conversations.flat_map { |link| Array(link.conversation&.messages) }
      .select { |message| message.direction == "user_to_client" }
      .max_by(&:sent_at)
  end

  def last_chase_send(invoice, sent = last_sent_outbox(invoice))
    outbound = last_outbound_message(invoice)
    sent_at = sent&.sent_at
    out_at = outbound&.sent_at
    if sent_at && (out_at.blank? || sent_at >= out_at)
      { at: sent_at, label: sent_step_label(sent, invoice) }
    elsif out_at
      { at: out_at, label: outbound.automatic? ? "a reminder" : "the invoice" }
    end
  end

  def sent_step_label(sent, invoice)
    return unless sent&.cadence_step

    copy = reminder_copy(sent.cadence_step, invoice)
    case copy[:kind]
    when "friendly" then "Friendly #{copy[:friendly_n]}"
    when "firm" then "Firm"
    when "final" then "Final"
    else STEP_LABELS[sent.cadence_step] || "a reminder"
    end
  end

  def days_late(invoice)
    return if invoice.due_date.blank?

    today = invoice.organization&.today || Date.current
    (today - invoice.due_date).to_i
  end

  def cadence_for(invoice, pending)
    if invoice.books_closed?
      { state: "closed", title: chase_result_for(invoice, last_sent_outbox(invoice)), detail: nil }
    elsif invoice.chase_status == "stopped"
      { state: "stopped", title: "Reminders off", detail: "You stopped this chase." }
    elsif pending&.status == "draft" && Cadence::Steps.draft?(pending.cadence_step)
      reminder_copy(pending.cadence_step, invoice).merge(state: "needs_approval", step: pending.cadence_step)
    elsif unmatched?(invoice)
      { state: "unmatched", title: "No Gmail thread linked", detail: "Match the invoice email before reminders can send." }
    elsif invoice.sleeping?
      {
        state: "sleeping",
        title: "Check back on #{short_date(invoice.expected_pay_date)}",
        detail: "If they reply sooner, this comes back to Needs you. If they don't, we'll bring it back on that date."
      }
    elsif pending&.status == "scheduled"
      reminder_copy(pending.cadence_step, invoice).merge(
        state: "queued",
        step: pending.cadence_step,
        detail: "Sends today at #{format_clock(pending.scheduled_send_at, invoice)} from your Gmail"
      )
    else
      next_ladder_step(invoice)
    end
  end

  def next_ladder_step(invoice)
    org = invoice.organization
    today = org&.today || Date.current
    Cadence::Steps.enabled_ladder(org).each do |row|
      offset = row[:offset]
      milestone = invoice.due_date + offset
      next if milestone < today

      copy = reminder_copy(row[:key], invoice, offset: offset)
      send_line = if milestone == today
        "Sends today at 10:15 AM from your Gmail"
      else
        "Sends #{short_date(milestone)} at 10:15 AM from your Gmail"
      end
      return copy.merge(state: "queued", detail: send_line, step: row[:key], offset: offset)
    end

    reminder_copy(Cadence::Steps::FIRM, invoice).merge(
      state: "needs_approval",
      step: Cadence::Steps::FIRM,
      detail: "Friendly is over. You send the next email."
    )
  end

  def reminder_copy(step, invoice, offset: nil)
    org = invoice.organization
    resolved = offset
    resolved = Cadence::Steps.offset_for(org, step) if resolved.nil?

    milestone = invoice.due_date + resolved
    case step.to_s
    when "firm_plus_7"
      { title: "Firm reminder — you send this", detail: "Automation never sends a firmer tone without you.", kind: "firm", offset: resolved }
    when "urgent_plus_14"
      { title: "Final reminder — you send this", detail: "Last email in the ladder. You click send.", kind: "final", offset: resolved }
    else
      index = Cadence::Steps::FRIENDLY.index(step.to_s)
      n = index ? index + 1 : 1
      {
        title: "Cadence: Friendly #{n} on #{short_date(milestone)}",
        detail: nil,
        kind: "friendly",
        offset: resolved,
        friendly_n: n
      }
    end
  end

  def chase_result_for(invoice, sent)
    return "Voided in QuickBooks" if invoice.books_status == "voided"
    return unless invoice.books_status == "paid"
    return "Paid — no reminder sent" if sent.blank?

    copy = reminder_copy(sent.cadence_step, invoice)
    "Paid after the #{copy[:title].to_s.sub(/ — you send this/, "").downcase}"
  end

  def stopped_at_for(invoice)
    return unless invoice.chase_status == "stopped"

    event = invoice.invoice_chase_events.select { |row| row.event_type == "stopped" }.max_by(&:created_at)
    (event&.created_at || invoice.updated_at)&.iso8601
  end

  def paid_at_for(invoice)
    return unless invoice.books_closed?

    if invoice.books_status == "voided"
      voided = invoice.invoice_chase_events.select { |row| row.event_type == "books_voided" }.max_by(&:created_at)
      return voided&.created_at || invoice.updated_at
    end

    paid_event(invoice)&.created_at || invoice.updated_at
  end

  def paid_via_for(invoice, event)
    return unless invoice.books_status == "paid"

    (event || paid_event(invoice))&.event_type.to_s == "books_paid" ? "quickbooks" : "manual"
  end

  def paid_event(invoice)
    invoice.invoice_chase_events.select { |row| row.event_type == "books_paid" }.max_by(&:created_at)
  end

  def suggested_wait_for(invoice)
    draft = invoice.outbox_messages.select { |row| %w[draft scheduled].include?(row.status) }
      .max_by(&:created_at)
    if draft&.suggested_wait_date
      return { date: draft.suggested_wait_date, quote: draft.suggested_wait_quote }
    end

    inbound_candidates(invoice).each do |message|
      found = Email::ParseWaitDate.extract(message.clean_body, as_of: message.sent_at)
      return found if found
    end
    nil
  end

  def inbound_candidates(invoice)
    [invoice.last_human_inbound_message, latest_thread_inbound(invoice)].compact.uniq
  end

  def latest_thread_inbound(invoice)
    invoice.invoice_conversations.flat_map { |link| Array(link.conversation&.messages) }
      .select { |message| message.direction == "client_to_user" }
      .max_by(&:sent_at)
  end

  def format_send_at(value, invoice)
    return unless value

    zone = invoice.organization&.zone || Time.zone
    value.in_time_zone(zone).strftime("%b %-d at %-I:%M %p")
  end

  def format_clock(value, invoice)
    return "10:15 AM" unless value

    zone = invoice.organization&.zone || Time.zone
    value.in_time_zone(zone).strftime("%-I:%M %p")
  end

  def short_date(value)
    value&.to_date&.strftime("%b %-d")
  end

  def iso_date(value)
    value&.to_date&.iso8601
  end
end
