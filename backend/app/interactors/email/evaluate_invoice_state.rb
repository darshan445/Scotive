# frozen_string_literal: true

# Email::EvaluateInvoiceState Interactor
# Purpose: human inbound pauses chase. Auto-reply / bounce does not. No status LLM.
# Methods:
# - execute

class Email::EvaluateInvoiceState
  include ExecuteMethodHelper
  include LogHelper
  include Invoices::ChaseWrite

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

      if invoice.books_closed?
        { skipped: true, reason: "books_closed", chase_status: invoice.chase_status }
      else
        apply_inbound!
        {
          skipped: false,
          chase_status: invoice.chase_status,
          list_bucket: invoice.list_bucket
        }
      end
    end
  end

  private

  attr_reader :invoice, :client

  def apply_inbound!
    inbound = invoice_messages.select { |message| message.direction == "client_to_user" }
    inbound.each do |message|
      next unless ignore_inbound?(message)

      message.update!(automatic: true) if !message.automatic?
      record_ignored!(message) unless already_event?(message)
    end

    human = inbound.reject { |message| ignore_inbound?(message) }.max_by(&:sent_at)
    if human.blank?
      unlink_ignored_splits!(invoice)
      clear_false_inbound!(invoice) if invoice.last_human_inbound_message_id.present?
      return
    end
    return if invoice.last_human_inbound_message_id == human.id

    apply_human_inbound!(invoice, human)
    suggest_wait!(human)
  end

  def record_ignored!(message)
    type = bounce?(message) ? "bounce_ignored" : "auto_reply_ignored"
    record_chase_event!(invoice, type: type, message: message, quote: message.clean_body.to_s.strip.truncate(160))
  end

  def already_event?(message)
    invoice.invoice_chase_events.exists?(message_id: message.id)
  end

  def ignore_inbound?(message)
    message.automatic? || bounce?(message) || noreply?(message) || auto_reply_subject?(message)
  end

  def auto_reply_subject?(message)
    message.conversation&.subject.to_s.match?(/\A\s*(automatic reply|auto[- ]reply|out of office|ooo:)/i)
  end

  def bounce?(message)
    message.from_address.to_s.match?(/mailer-daemon|postmaster/i) ||
      message.clean_body.to_s.match?(/delivery status notification|undeliverable/i)
  end

  def noreply?(message)
    local = message.from_address.to_s.split("@", 2).first.to_s.downcase
    local.match?(/\A(no[-_]?reply|do[-_]?not[-_]?reply|noreply|notifications?|newsletter|mailer|digest|updates?)\z/)
  end

  def suggest_wait!(message)
    parsed = Email::ParseWaitDate.extract(message.clean_body, as_of: message.sent_at)
    return if parsed.blank?

    draft = pending_draft
    return if draft.blank?

    draft.update!(suggested_wait_date: parsed[:date], suggested_wait_quote: parsed[:quote])
  end

  def pending_draft
    invoice.outbox_messages.pending.order(created_at: :desc).first
  end

  def invoice_messages
    Message.joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: invoice.id })
      .order(:sent_at)
  end

  def unlink_ignored_splits!(invoice)
    invoice.invoice_conversations.includes(conversation: :messages).where(is_primary: false).find_each do |link|
      inbound = link.conversation.messages.select { |message| message.direction == "client_to_user" }
      next if inbound.empty? || inbound.any? { |message| !ignore_inbound?(message) }

      link.destroy!
    end
    invoice.invoice_conversations.reset
  end
end
