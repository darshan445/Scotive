# frozen_string_literal: true

# Email::EvaluateInvoiceState Interactor
# Purpose: AR Step 5 — one-invoice AI State Reader (rulebook_reeval). No cadence.
# Methods:
# - execute

class Email::EvaluateInvoiceState
  include ExecuteMethodHelper
  include LogHelper

  PROMPT_PATH = Rails.root.join("prompts/rulebook_reeval.txt")
  ALLOWED_STATUSES = %w[invoiced overdue promised broken_promise disputed paid_unconfirmed partially_paid].freeze
  WEEKDAYS = {
    "sunday" => 0, "monday" => 1, "tuesday" => 2, "wednesday" => 3,
    "thursday" => 4, "friday" => 5, "saturday" => 6
  }.freeze

  def self.execute(invoice:, client: Email::LlmClient.new)
    new(invoice: invoice, client: client).execute
  end

  def initialize(invoice:, client:)
    @invoice = invoice
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invoice is required") if invoice.blank?

      if skip?
        { skipped: true, status: invoice.current_ar_status }
      else
        raw = call_reader!
        commit!(raw)
        {
          skipped: false,
          status: invoice.current_ar_status,
          needs_reply: invoice.needs_reply,
          events: Array(raw["new_events"]).size
        }
      end
    end
  end

  private

  attr_reader :invoice, :client

  def skip?
    terminal? || messages.none? { |message| message.direction == "client_to_user" }
  end

  def terminal?
    invoice.balance_remaining.to_d <= 0 || %w[paid voided].include?(invoice.current_ar_status)
  end

  def call_reader!
    raw = client.complete_json(system: prompt, user: payload.to_json)
    raise_string_error("State reader returned invalid JSON") unless raw.is_a?(Hash)

    raw.stringify_keys
  rescue Faraday::Error, KeyError
    raise_string_error("State reader failed")
  end

  def commit!(raw)
    status = normalize_status(raw["status"])
    needs_reply = ActiveModel::Type::Boolean.new.cast(raw["needs_reply"]) || false
    events = Array(raw["new_events"]).map { |event| event.stringify_keys }
    promise_date = resolved_promise_date(status, events, raw["promise_date"])
    status = "broken_promise" if status == "promised" && promise_date.present? && promise_date < Date.current
    disputed = parse_amount(raw["disputed_claim_amount"])
    disputed = nil unless status == "disputed" || (disputed.present? && status == "partially_paid")
    promise_date = nil if %w[invoiced overdue paid_unconfirmed].include?(status)
    trigger_message = message_for(events.last)
    previous_status = invoice.current_ar_status
    previous_needs_reply = invoice.needs_reply
    previous_promise = invoice.active_promise_date
    previous_disputed = invoice.disputed_claim_amount

    ActiveRecord::Base.transaction do
      persist_events!(events)
      invoice.update!(
        current_ar_status: status,
        needs_reply: needs_reply,
        active_promise_date: promise_date,
        disputed_claim_amount: disputed
      )
      changed = previous_status != status || previous_needs_reply != needs_reply ||
        previous_promise != promise_date || previous_disputed != disputed
      if changed || events.any?
        invoice.invoice_state_transitions.create!(
          from_status: previous_status,
          to_status: status,
          trigger_source: "ai_reader",
          triggered_by_message: trigger_message,
          promise_date: promise_date,
          disputed_amount: disputed,
          needs_reply: needs_reply,
          reason_quote: events.last&.dig("quote").to_s.presence,
          created_at: Time.current
        )
      end
      messages.each { |message| message.update!(processed_by_ai: true) unless message.processed_by_ai? }
    end
  end

  def persist_events!(events)
    events.each do |event|
      type = event["type"].to_s
      next if type.blank?

      sender = event["sender"].to_s == "user" ? "user" : "client"
      invoice.invoice_events.create!(
        message: message_for(event),
        event_type: type,
        sender: sender,
        quote: event["quote"].to_s.presence,
        event_data: event["data"].is_a?(Hash) ? event["data"] : {},
        confidence: event["confidence"],
        created_at: Time.current
      )
    end
  end

  def normalize_status(value)
    status = value.to_s
    status = "paid_unconfirmed" if status == "paid"
    status = books_status if status.blank? || status == "unmatched" || !ALLOWED_STATUSES.include?(status)
    status
  end

  def resolved_promise_date(status, events, header_date)
    standing = invoice.active_promise_date
    events.each do |event|
      case event["type"].to_s
      when "promise"
        standing = calendar_date_for(event) || standing
      when "promise_retract", "paid_claim"
        standing = nil
      end
    end
    standing = parse_date(header_date) if standing.blank?
    standing
  end

  def calendar_date_for(event)
    data = event["data"].is_a?(Hash) ? event["data"].stringify_keys : {}
    explicit = parse_date(data["date"])
    return explicit if explicit

    anchor = parse_date(data["anchor_date"]) || message_for(event)&.sent_at&.to_date
    resolve_relative(data["relative_phrase"].to_s, anchor)
  end

  def resolve_relative(phrase, anchor)
    return if phrase.blank? || anchor.blank?

    text = phrase.downcase
    return anchor if text.match?(/\btoday\b|\btonight\b|\beod\b/)
    return anchor + 1 if text.match?(/\btomorrow\b/)
    return (anchor + (text.include?("next") ? 7 : 0)).end_of_week(:sunday) if text.match?(/end of (the )?week|this week|next week/) && WEEKDAYS.keys.none? { |day| text.include?(day) }

    WEEKDAYS.each do |name, wday|
      next unless text.include?(name)

      delta = (wday - anchor.wday) % 7
      delta = 7 if delta.zero? && text.include?("next")
      return anchor + delta
    end

    parse_date(phrase)
  end

  def message_for(event)
    return if event.blank?

    id = event["message_id"].to_s
    return if id.blank?

    messages.find { |message| message.external_message_id == id }
  end

  def messages
    @messages ||= Message.joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: invoice.id })
      .includes(conversation: :integration)
      .order(:sent_at)
      .to_a
  end

  def payload
    client_row = invoice.client
    {
      user_email: user_email,
      client_email: client_row.primary_email,
      associated_client_emails: Array(client_row.associated_emails).map { |email| email.to_s.downcase } - [ client_row.primary_email.to_s.downcase ],
      anchor_invoice_ref: invoice.invoice_number,
      tracked_state: {
        invoice_ref: invoice.invoice_number,
        amount: invoice.total_amount.to_f,
        currency: invoice.currency,
        due_date: invoice.due_date.iso8601,
        due_date_status: "explicit",
        status: books_status,
        promise_date: nil,
        paid_amount: paid_amount.to_f,
        balance_remaining: invoice.balance_remaining.to_f,
        disputed_claim_amount: nil,
        as_of_date: Date.current.iso8601,
        processed_message_ids: messages.select(&:processed_by_ai?).map(&:external_message_id)
      },
      messages: messages.map { |message| message_payload(message) }
    }
  end

  def message_payload(message)
    {
      id: message.external_message_id,
      thread_id: message.conversation.external_thread_id,
      date: message.sent_at.utc.iso8601,
      direction: message.direction,
      from: message.from_address,
      to: Array(message.to_addresses),
      cc: Array(message.cc_addresses),
      subject: message.conversation.subject.to_s,
      body: message.clean_body.to_s,
      attachment_names: [],
      pdf_text: nil,
      is_anchor: message.is_anchor?
    }
  end

  def user_email
    mailbox = messages.first&.conversation&.integration
    mailbox&.account_name.presence || invoice.organization.users.order(:created_at).first&.email
  end

  def books_status
    invoice.due_date < Date.current ? "overdue" : "invoiced"
  end

  def paid_amount
    amount = invoice.total_amount.to_d - invoice.balance_remaining.to_d
    amount.negative? ? 0 : amount
  end

  def prompt
    File.read(PROMPT_PATH)
  end

  def parse_date(value)
    return if value.blank?
    return value if value.is_a?(Date)

    Date.iso8601(value.to_s)
  rescue ArgumentError
    Date.parse(value.to_s) rescue nil
  end

  def parse_amount(value)
    return if value.blank?

    BigDecimal(value.to_s)
  rescue ArgumentError
    nil
  end
end
