# frozen_string_literal: true

# Invoices::DraftChase Interactor
# Purpose: classify the reply job, draft only when the outcome is known, attach a pay-link template.
# Methods:
# - execute

class Invoices::DraftChase
  include ExecuteMethodHelper
  include LogHelper

  PROMPT_PATH = Rails.root.join("prompts/draft_chase.txt")
  JOBS = %w[chase broken_date answer_facts decision].freeze
  AUTO_DRAFT_JOBS = %w[chase broken_date answer_facts].freeze
  TONE_LABELS = {
    "notice_minus_3" => "Friendly reminder",
    "due_today" => "Friendly reminder",
    "nudge_plus_3" => "Friendly reminder",
    "firm_plus_7" => "Firm follow-up",
    "urgent_plus_14" => "Final notice",
    "broken_promise" => "Broken promise"
  }.freeze
  JOB_REASONS = {
    "chase" => "A payment reminder. Edit if you want it shorter or firmer.",
    "broken_date" => "They named a date that passed.",
    "answer_facts" => "They asked something we can answer from the invoice.",
    "decision" => "They asked for something only you can decide. Tell us what to send — e.g. invoice stands, or offer $X."
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
      raise_string_error("Invoice is paid") if invoice.books_closed?

      conversation = reply_conversation(invoice)
      pending = pending_draft(invoice)
      step = step_for(invoice, pending)
      llm = llm_copy(invoice, conversation, step)
      assemble(invoice, conversation, pending, step, llm)
    end
  end

  private

  attr_reader :organization, :invoice_id, :note, :intent, :client

  def pending_draft(invoice)
    invoice.outbox_messages.pending.order(created_at: :desc).first
  end

  def step_for(invoice, pending)
    return pending.cadence_step if pending&.cadence_step.present?
    return "broken_promise" if invoice.wait_expired?
    return intent_step if intent_step.present?
    return Cadence::Steps::FIRM if invoice.past_friendly_window?

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
    invoice.list_bucket == "needs_you"
  end

  def assemble(invoice, conversation, pending, step, llm)
    job = normalize_job(llm&.dig("job")) || fallback_job(invoice)
    instructed = note.present?
    can_draft = AUTO_DRAFT_JOBS.include?(job) || instructed
    reason = llm&.dig("reason").presence || JOB_REASONS[job]
    payload = {
      subject: llm&.dig("subject").presence || pending&.subject.presence || Cadence::Copy.subject(invoice, conversation),
      body: "",
      tone_label: TONE_LABELS[step] || (reply?(invoice) ? "Reply" : "Follow-up"),
      is_reply: reply?(invoice),
      cadence_step: step,
      outbox_id: pending&.id,
      job: job,
      reason: reason,
      needs_instruction: !can_draft,
      include_pay_link: false,
      instruction_hint: instruction_hint(job)
    }
    return payload unless can_draft

    body = Cadence::Copy.strip_pay_urls(llm&.dig("body").to_s, invoice)
    if body.blank? && silent?(invoice)
      body = pending&.body.presence || Cadence::Copy.body_without_pay(invoice, step)
      body = "#{note}\n\n#{body}" if instructed && llm.blank? && pending.blank?
    end
    if body.blank?
      payload[:needs_instruction] = true
      payload[:reason] = instructed ? "Couldn't draft that. Try a shorter instruction." : reason
      return payload
    end

    include_link = pay_link?(invoice, job, llm, silent: silent?(invoice) && llm.blank?)
    payload.merge(
      body: body,
      needs_instruction: false,
      include_pay_link: include_link,
      mail_preview: Cadence::MailTemplate.preview(invoice, include_pay_link: include_link)
    )
  end

  def fallback_job(invoice)
    return "chase" if silent?(invoice)
    return "broken_date" if invoice.wait_expired?

    "decision"
  end

  def silent?(invoice)
    invoice.last_human_inbound_at.blank?
  end

  def pay_link?(invoice, job, llm, silent:)
    return false if invoice.pay_link_token.to_s.strip.blank?
    return true if silent && llm.blank?
    return false if llm.blank?

    llm["include_pay_link"] == true
  end

  def instruction_hint(job)
    if job == "decision"
      "e.g. invoice stands, or offer $1,800 if they pay this week"
    else
      "Optional: shorter, mention the PO, change the tone"
    end
  end

  def normalize_job(value)
    key = value.to_s.strip.downcase
    JOBS.include?(key) ? key : nil
  end

  def llm_copy(invoice, conversation, step)
    raw = client.complete_json(system: prompt, user: payload(invoice, conversation, step).to_json, temperature: 0.3)
    return unless raw.is_a?(Hash)

    data = raw.stringify_keys
    {
      "job" => normalize_job(data["job"]),
      "include_pay_link" => data["include_pay_link"] == true || data["include_pay_link"].to_s == "true",
      "reason" => data["reason"].to_s.strip.presence,
      "subject" => data["subject"].to_s.strip.presence,
      "body" => data["body"].to_s.strip.presence
    }
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
      expected_pay_date: invoice.expected_pay_date&.iso8601,
      status: invoice.list_bucket,
      chase_status: invoice.chase_status,
      books_status: invoice.books_status,
      needs_you: invoice.list_bucket == "needs_you",
      pay_link_available: invoice.pay_link_token.to_s.strip.present?,
      client_name: invoice.client&.name,
      client_email: invoice.client&.primary_email,
      cadence_step: step,
      tone_label: TONE_LABELS[step],
      existing_subject: conversation&.subject,
      steer_note: note.presence,
      last_client_message: last_client_body(invoice),
      owner_voice: owner_voice(invoice),
      recent_messages: recent_messages(invoice)
    }
  end

  def reply_conversation(invoice)
    inbound = invoice.last_human_inbound_message
    return inbound.conversation if inbound&.conversation.present?

    last = linked_messages(invoice).where(direction: "client_to_user").order(sent_at: :desc).first
    last&.conversation || Ledger::InvoicePayload.primary_conversation(invoice)
  end

  def last_client_body(invoice)
    invoice.last_human_inbound_message&.clean_body.presence ||
      linked_messages(invoice).where(direction: "client_to_user").order(sent_at: :desc).first&.clean_body
  end

  def owner_voice(invoice)
    linked_messages(invoice).where(direction: "user_to_client").order(sent_at: :desc).limit(2).reverse.map do |message|
      { sent_at: message.sent_at&.iso8601, body: message.clean_body.to_s.truncate(800) }
    end
  end

  def recent_messages(invoice)
    linked_messages(invoice).order(sent_at: :desc).limit(8).reverse.map do |message|
      {
        direction: message.direction,
        sent_at: message.sent_at&.iso8601,
        body: message.clean_body.to_s.truncate(1200)
      }
    end
  end

  def linked_messages(invoice)
    Message.joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: invoice.id })
  end

  def prompt
    @prompt ||= File.read(PROMPT_PATH)
  end
end
