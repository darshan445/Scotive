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
    payload = send_with_live_parent!(
      client: client,
      mailbox: mailbox,
      conversation: conversation,
      to: to,
      cc: cc,
      subject: subject,
      html: mail[:html],
      attachments: attachments
    )
    persist_delivered!(invoice, conversation, mailbox, payload, to: to, cc: cc, subject: subject, body: prose, outbox: outbox)
  rescue Faraday::Error => e
    raise_string_error(e.message.to_s.presence || "Mailbox send failed")
  end

  PARENT_GONE = /parent_mail_not_found|parent_mail_invalid|invalid_reply_to|email not found/i

  def send_with_live_parent!(client:, mailbox:, conversation:, to:, cc:, subject:, html:, attachments:)
    parents = unipile_reply_candidates(client, mailbox, conversation)
    last_error = nil
    (parents + [ nil ]).uniq.each do |reply_to|
      begin
        return client.send_email(
          account_id: mailbox.external_account_id,
          to: to,
          cc: Array(cc),
          subject: subject,
          body: html,
          reply_to: reply_to,
          custom_headers: [
            { name: "X-Auto-Response-Suppress", value: "All" }
          ],
          attachments: Array(attachments)
        )
      rescue Faraday::Error => e
        last_error = e
        next if PARENT_GONE.match?(e.message) && reply_to.present?

        raise
      end
    end
    raise last_error if last_error

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

  # Live Unipile ids on this mailbox first. Stored Gmail hex / stale ids are only hints.
  def unipile_reply_candidates(client, mailbox, conversation)
    ids = live_thread_email_ids(client, mailbox, conversation)
    conversation.messages.order(sent_at: :desc).each do |message|
      resolved = verify_unipile_email_id(client, mailbox.external_account_id, message.external_message_id)
      next if resolved.blank? || ids.include?(resolved)

      ids << resolved
      remember_unipile_id!(message, resolved)
    end
    ids
  end

  def live_thread_email_ids(client, mailbox, conversation)
    thread_id = conversation.external_thread_id.to_s
    return [] if thread_id.blank?

    body = client.list_emails(account_id: mailbox.external_account_id, thread_id: thread_id, limit: 20)
    items = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
    items.filter_map { |row| live_row_id(row) }
  rescue Faraday::Error
    []
  end

  def live_row_id(row)
    return unless row.is_a?(Hash)

    id = row["id"].presence || row[:id].presence || row["email_id"].presence
    id if unipile_email_id?(id)
  end

  def verify_unipile_email_id(client, account_id, stored)
    token = stored.to_s.strip
    return if token.blank? || token.start_with?("outbox:")

    row = client.get_email(token, account_id: account_id)
    live_row_id(row)
  rescue Faraday::Error
    nil
  end

  def remember_unipile_id!(message, resolved)
    return if resolved.blank? || message.external_message_id == resolved

    message.update!(external_message_id: resolved)
  rescue ActiveRecord::RecordNotUnique, ActiveRecord::RecordInvalid
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
