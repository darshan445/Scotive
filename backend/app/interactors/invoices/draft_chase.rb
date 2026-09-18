# frozen_string_literal: true

# Invoices::DraftChase Interactor
# Purpose: LLM Follow-up / Reply copy with template fallback (no send).
# Methods:
# - execute

class Invoices::DraftChase
  include ExecuteMethodHelper
  include LogHelper

  PROMPT_PATH = Rails.root.join("prompts/draft_chase.txt")
  TONE_LABELS = {
    "notice_minus_3" => "Friendly reminder",
    "due_today" => "Friendly reminder",
    "nudge_plus_3" => "Friendly reminder",
    "firm_plus_7" => "Firm follow-up",
    "urgent_plus_14" => "Final notice",
    "broken_promise" => "Broken promise"
  }.freeze

  def self.execute(organization:, invoice_id:, note: nil, intent: nil, client: Email::LlmClient.new)
    new(organization: organization, invoice_id: invoice_id, note: note, intent: intent, client: client).execute
  end

  def initialize(organization:, invoice_id:, note:, intent:, client:)
    @organization = organization
    @invoice_id = invoice_id
    @note = note.to_s.strip
    @intent = intent.to_s.strip
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      invoice = organization.invoices.find_by(id: invoice_id)
      raise_string_error("Invoice not found") if invoice.blank?
      raise_string_error("Invoice is paid") if %w[paid voided].include?(invoice.current_ar_status)

      conversation = Ledger::InvoicePayload.primary_conversation(invoice)
      pending = pending_draft(invoice)
      step = step_for(invoice, pending)
      llm = llm_copy(invoice, conversation, step)
      body = llm&.dig("body").presence || pending&.body.presence || Cadence::Copy.body(invoice, step)
      body = "#{note}\n\n#{body}" if note.present? && llm.blank?
      {
        subject: llm&.dig("subject").presence || pending&.subject.presence || Cadence::Copy.subject(invoice, conversation),
        body: body,
        tone_label: TONE_LABELS[step] || (reply?(invoice) ? "Reply" : "Follow-up"),
        is_reply: reply?(invoice),
        cadence_step: step,
        outbox_id: pending&.id
      }
    end
  end

  private

  attr_reader :organization, :invoice_id, :note, :intent, :client

  def pending_draft(invoice)
    invoice.outbox_messages.pending.order(created_at: :desc).first
  end

  def step_for(invoice, pending)
    return pending.cadence_step if pending&.cadence_step.present?
    return "broken_promise" if invoice.current_ar_status == "broken_promise"
    return intent_step if intent_step.present?

    Cadence::Steps.current_key(organization, invoice)
  end

  def intent_step
    case intent
    when "firm", "firm_followup" then "firm_plus_7"
    when "final", "final_notice", "urgent" then "urgent_plus_14"
    when "broken_promise", "promise_broken" then "broken_promise"
    when "friendly", "friendly_followup" then "nudge_plus_3"
    end
  end

  def reply?(invoice)
    invoice.needs_reply || invoice.current_ar_status == "disputed"
  end

  def llm_copy(invoice, conversation, step)
    raw = client.complete_json(system: prompt, user: payload(invoice, conversation, step).to_json, temperature: 0.3)
    return unless raw.is_a?(Hash)

    data = raw.stringify_keys
    body = data["body"].to_s.strip
    return if body.blank?

    { "subject" => data["subject"].to_s.strip.presence, "body" => body }
  rescue Faraday::Error, KeyError
    nil
  end

  def payload(invoice, conversation, step)
    {
      invoice_number: invoice.invoice_number,
      amount: invoice.total_amount.to_s,
      remaining: invoice.balance_remaining.to_s,
      currency: invoice.currency,
      due_date: invoice.due_date&.iso8601,
      promise_date: invoice.active_promise_date&.iso8601,
      status: invoice.current_ar_status,
      needs_reply: invoice.needs_reply,
      pay_link: invoice.pay_link_token,
      client_name: invoice.client&.name,
      client_email: invoice.client&.primary_email,
      cadence_step: step,
      tone_label: TONE_LABELS[step],
      existing_subject: conversation&.subject,
      steer_note: note.presence,
      recent_messages: recent_messages(conversation)
    }
  end

  def recent_messages(conversation)
    return [] if conversation.blank?

    conversation.messages.order(sent_at: :desc).limit(8).reverse.map do |message|
      {
        direction: message.direction,
        sent_at: message.sent_at&.iso8601,
        body: message.clean_body.to_s.truncate(1200)
      }
    end
  end

  def prompt
    @prompt ||= File.read(PROMPT_PATH)
  end
end
