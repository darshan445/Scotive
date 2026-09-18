# frozen_string_literal: true

# Cadence::Dispatch Interactor
# Purpose: five pre-flight guards, send Friendly on the Home Thread, persist the outbound message.
# Methods:
# - execute

class Cadence::Dispatch
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  def self.execute(outbox_message:, client: Email::EmailClient.new)
    new(outbox_message: outbox_message, client: client).execute
  end

  def initialize(outbox_message:, client:)
    @outbox_message = outbox_message
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Outbox message is required") if outbox_message.blank?

      outcome = nil
      Invoice.transaction do
        invoice = organization.invoices.lock.find(outbox_message.invoice_id)
        row = organization.outbox_messages.lock.find(outbox_message.id)
        outcome = if row.status != "scheduled"
          { skipped: true, reason: "not_scheduled" }
        else
          reason = guard_reason(invoice)
          if reason
            cancel!(row, reason)
            { cancelled: true, reason: reason }
          else
            send_and_persist!(invoice, row)
          end
        end
      end
      outcome
    end
  end

  private

  attr_reader :outbox_message, :client

  def organization
    outbox_message.organization
  end

  def guard_reason(invoice)
    if invoice.balance_remaining.to_d <= 0 || %w[paid voided].include?(invoice.current_ar_status)
      "paid_in_books"
    elsif invoice.needs_reply
      "client_awaiting_human_reply"
    elsif %w[disputed paid_unconfirmed promised].include?(invoice.current_ar_status)
      "blocked_by_status"
    elsif invoice.snoozed_until.present? && invoice.snoozed_until > Time.current
      "invoice_snoozed_by_user"
    elsif fatigue?(invoice)
      "anti_fatigue_cooldown"
    end
  end

  def fatigue?(invoice)
    since = 48.hours.ago
    client_invoice_ids = organization.invoices.where(client_id: invoice.client_id).select(:id)
    sent = OutboxMessage.where(invoice_id: client_invoice_ids, status: "sent")
      .where("sent_at > ?", since)
      .where.not(id: outbox_message.id)
    return true if sent.exists?

    Message.joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: client_invoice_ids })
      .where(direction: "user_to_client")
      .where("messages.sent_at > ?", since)
      .exists?
  end

  def send_and_persist!(invoice, row)
    conversation = home_thread(invoice)
    raise_string_error("Home thread is missing") if conversation.blank?

    mailbox = conversation.integration
    raise_string_error("Mailbox is not connected") if mailbox.blank? || !mailbox.connected? || mailbox.external_account_id.blank?

    last_message = conversation.messages.order(:sent_at).last
    raise_string_error("Home thread has no messages") if last_message.blank?

    payload = client.send_email(
      account_id: mailbox.external_account_id,
      to: row.to_address,
      cc: Array(row.cc_addresses),
      subject: row.subject,
      body: row.body,
      reply_to: last_message.external_message_id,
      custom_headers: mime_headers(conversation, last_message)
    )
    persist_sent!(invoice, row, conversation, mailbox, payload)
    { sent: true, outbox_id: row.id }
  rescue Faraday::Error
    raise_string_error("Mailbox send failed")
  end

  def persist_sent!(invoice, row, conversation, mailbox, payload)
    external_id = sent_id(payload).presence || "outbox:#{row.id}"
    persist_message!(
      conversation,
      {
        id: external_id,
        from: mailbox.account_name.presence || row.to_address,
        to: [ row.to_address ],
        cc: Array(row.cc_addresses),
        sent_at: Time.current,
        clean_body: row.body
      },
      normalize_email(mailbox.account_name),
      anchor: false
    )
    row.update!(status: "sent", sent_at: Time.current)
    invoice.update!(needs_reply: false)
  end

  def mime_headers(conversation, last_message)
    anchor = conversation.messages.find_by(is_anchor: true) || conversation.messages.order(:sent_at).first
    references = [ anchor&.external_message_id, last_message.external_message_id ].compact.uniq
    [
      { name: "In-Reply-To", value: "<#{last_message.external_message_id}>" },
      { name: "References", value: references.map { |id| "<#{id}>" }.join(" ") }
    ]
  end

  def home_thread(invoice)
    link = invoice.invoice_conversations.find_by(is_primary: true)
    conversation = link&.conversation
    conversation ||= row_conversation(invoice)
    conversation
  end

  def row_conversation(invoice)
    conversation = outbox_message.conversation
    return if conversation.blank?
    return unless conversation.organization_id == invoice.organization_id

    conversation
  end

  def sent_id(payload)
    return unless payload.is_a?(Hash)

    payload["id"].presence || payload[:id].presence
  end

  def cancel!(row, reason)
    row.update!(status: "cancelled", cancellation_reason: reason)
  end
end
