# frozen_string_literal: true

# Send a reply on the invoice Home Thread (Unipile + RFC In-Reply-To / References).
module Cadence::HomeThreadSend
  include Email::MailboxThreadPersistence
  include Invoices::ChaseWrite

  def deliver_home_thread!(invoice:, to:, cc:, subject:, body:, client:, outbox: nil)
    conversation = home_thread_for(invoice, outbox)
    raise_string_error("Home thread is missing") if conversation.blank?

    mailbox = conversation.integration
    raise_string_error("Mailbox is not connected") if mailbox.blank? || !mailbox.connected? || mailbox.external_account_id.blank?

    last_message = conversation.messages.order(:sent_at).last
    raise_string_error("Home thread has no messages") if last_message.blank?

    payload = client.send_email(
      account_id: mailbox.external_account_id,
      to: to,
      cc: Array(cc),
      subject: subject,
      body: body,
      reply_to: last_message.external_message_id,
      custom_headers: mime_headers(conversation, last_message)
    )
    persist_delivered!(invoice, conversation, mailbox, payload, to: to, cc: cc, subject: subject, body: body, outbox: outbox)
  rescue Faraday::Error
    raise_string_error("Mailbox send failed")
  end

  def persist_delivered!(invoice, conversation, mailbox, payload, to:, cc:, subject:, body:, outbox:)
    external_id = sent_id(payload).presence || "outbox:#{outbox&.id || SecureRandom.uuid}"
    persist_message!(
      conversation,
      {
        id: external_id,
        from: mailbox.account_name.presence || to,
        to: [ to ],
        cc: Array(cc),
        sent_at: Time.current,
        clean_body: body
      },
      normalize_email(mailbox.account_name),
      anchor: false
    )
    outbox.update!(status: "sent", sent_at: Time.current, subject: subject, body: body) if outbox
    type = outbox && Cadence::Steps.friendly?(outbox.cadence_step) ? "friendly_sent" : "draft_sent"
    record_chase_event!(invoice, type: type)
    { sent: true, message_id: external_id, outbox_id: outbox&.id }
  end

  def mime_headers(conversation, last_message)
    anchor = conversation.messages.find_by(is_anchor: true) || conversation.messages.order(:sent_at).first
    references = [ anchor&.external_message_id, last_message.external_message_id ].compact.uniq
    [
      { name: "In-Reply-To", value: "<#{last_message.external_message_id}>" },
      { name: "References", value: references.map { |id| "<#{id}>" }.join(" ") },
      { name: "Auto-Submitted", value: "auto-generated" },
      { name: "X-Auto-Response-Suppress", value: "All" }
    ]
  end

  def home_thread_for(invoice, outbox)
    link = invoice.invoice_conversations.find_by(is_primary: true)
    conversation = link&.conversation
    fallback = outbox&.conversation
    if conversation.blank? && fallback.present? && fallback.organization_id == invoice.organization_id
      conversation = fallback
    end
    conversation
  end

  def sent_id(payload)
    return unless payload.is_a?(Hash)

    payload["id"].presence || payload[:id].presence
  end
end
