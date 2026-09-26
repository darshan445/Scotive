# frozen_string_literal: true

# Send a reply via Unipile (reply_to = provider id). Cadence stays on the Home Thread.
# User Follow-up uses the thread the client last wrote on (home or a new compose).
# Unipile only accepts custom headers that start with X-.
module Cadence::HomeThreadSend
  include Email::MailboxThreadPersistence
  include Invoices::ChaseWrite

  def deliver_home_thread!(invoice:, to:, cc:, subject:, body:, client:, outbox: nil, conversation: nil, include_pay_link: nil, attachments: [])
    conversation ||= home_thread_for(invoice, outbox)
    raise_string_error("Home thread is missing") if conversation.blank?

    mailbox = conversation.integration
    raise_string_error("Mailbox is not connected") if mailbox.blank? || !mailbox.connected? || mailbox.external_account_id.blank?

    last_message = conversation.messages.order(:sent_at).last
    raise_string_error("Thread has no messages") if last_message.blank?

    pay = include_pay_link.nil? ? invoice.pay_link_token.to_s.match?(/\Ahttps?:\/\//i) : include_pay_link
    prose = Cadence::Copy.strip_pay_urls(body, invoice)
    mail = Cadence::MailTemplate.for(invoice, prose: prose, include_pay_link: pay)
    reply_to = unipile_reply_to(client, mailbox, conversation)
    payload = client.send_email(
      account_id: mailbox.external_account_id,
      to: to,
      cc: Array(cc),
      subject: subject,
      body: mail[:html],
      reply_to: reply_to,
      custom_headers: [
        { name: "X-Auto-Response-Suppress", value: "All" }
      ],
      attachments: Array(attachments)
    )
    persist_delivered!(invoice, conversation, mailbox, payload, to: to, cc: cc, subject: subject, body: prose, outbox: outbox)
  rescue Faraday::Error => e
    raise_string_error(e.message.to_s.presence || "Mailbox send failed")
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
    if outbox
      outbox.update!(
        status: "sent",
        sent_at: Time.current,
        subject: subject,
        body: body,
        conversation: conversation
      )
    end
    type = outbox && Cadence::Steps.friendly?(outbox.cadence_step) ? "friendly_sent" : "draft_sent"
    record_chase_event!(invoice, type: type)
    { sent: true, message_id: external_id, outbox_id: outbox&.id }
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

  # Last client mail on any linked thread (new compose or Home). Otherwise Home Thread.
  def reply_thread_for(invoice, outbox)
    inbound = invoice.last_human_inbound_message
    return inbound.conversation if inbound&.conversation.present?

    last_inbound = Message
      .joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: invoice.id }, direction: "client_to_user")
      .order(sent_at: :desc)
      .first
    last_inbound&.conversation || home_thread_for(invoice, outbox)
  end

  def reply_address_for(invoice, conversation)
    last_message = conversation.messages.order(:sent_at).last
    if last_message&.direction == "client_to_user"
      last_message.from_address.presence || invoice.client.primary_email
    else
      Array(last_message&.to_addresses).first.presence || invoice.client.primary_email
    end
  end

  def threaded_subject(conversation, requested)
    parent = conversation&.subject.to_s.strip
    return requested if parent.blank?

    bare_parent = parent.sub(/\A(?:re|fw|fwd)\s*:\s*/i, "")
    bare_requested = requested.to_s.sub(/\A(?:re|fw|fwd)\s*:\s*/i, "")
    return requested if bare_requested.casecmp?(bare_parent)

    parent.match?(/\A(?:re|fw|fwd)\s*:/i) ? parent : "Re: #{parent}"
  end

  def sent_id(payload)
    return unless payload.is_a?(Hash)

    payload["id"].presence || payload[:id].presence
  end

  # Unipile reply_to must be their email id, not a Gmail hex provider_id or RFC Message-ID.
  def unipile_reply_to(client, mailbox, conversation)
    account_id = mailbox.external_account_id
    conversation.messages.order(sent_at: :desc).each do |message|
      resolved = resolve_unipile_email_id(client, account_id, message.external_message_id)
      return resolved if resolved.present?
    end
    nil
  end

  def resolve_unipile_email_id(client, account_id, stored)
    token = stored.to_s.strip
    return if token.blank? || token.start_with?("outbox:")
    return token if unipile_email_id?(token)

    row = client.get_email(token, account_id: account_id)
    return unless row.is_a?(Hash)

    id = row["id"].presence || row[:id].presence || row["email_id"].presence
    id if unipile_email_id?(id)
  rescue Faraday::Error
    nil
  end

  def unipile_email_id?(value)
    token = value.to_s.strip
    return false if token.blank?
    return false if token.match?(/\A[0-9a-f]{10,}\z/i)
    return false if token.include?("@")

    true
  end
end
