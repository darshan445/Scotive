# frozen_string_literal: true

require "cgi"
require "set"

# Shared Home/Split persist + A/B/C match predicates for mailbox historical match
# and per-invoice fallback. Not an interactor.
module Email::MailboxThreadPersistence
  AMOUNT_PATTERN = /(?:usd|us\$|\$)?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?/i

  def persist_thread!(mailbox, invoice, thread_id, messages, primary:)
    thread_messages = messages.select { |message| message[:thread_id] == thread_id }.sort_by { |message| message[:sent_at] }
    return if thread_messages.empty?

    conversation = organization.conversations.find_or_initialize_by(
      integration_id: mailbox.id,
      external_thread_id: thread_id
    )
    conversation.organization = organization
    conversation.integration = mailbox
    conversation.subject ||= thread_messages.first[:subject]
    conversation.status = "active"
    raise_string_error(conversation.errors.full_messages.to_sentence) unless conversation.save

    link = InvoiceConversation.find_or_initialize_by(invoice_id: invoice.id, conversation_id: conversation.id)
    link.is_primary = true if primary
    link.created_at ||= Time.current
    raise_string_error(link.errors.full_messages.to_sentence) unless link.save
    invoice.invoice_conversations.reset

    owner_email = normalize_email(mailbox.account_name)
    thread_messages.each_with_index do |message, index|
      persist_message!(conversation, message, owner_email, anchor: index.zero? && direction_for(message, owner_email) == "user_to_client")
    end
  end

  def persist_message!(conversation, message, owner_email, anchor:)
    record = conversation.messages.find_or_initialize_by(external_message_id: message[:id])
    record.direction = direction_for(message, owner_email)
    record.from_address = message[:from]
    record.to_addresses = message[:to]
    record.cc_addresses = message[:cc]
    record.sent_at = message[:sent_at]
    record.clean_body = message[:clean_body]
    record.is_anchor = true if anchor || record.is_anchor?
    record.created_at ||= Time.current
    raise_string_error(record.errors.full_messages.to_sentence) unless record.save
  end

  def invoice_has_home_thread?(invoice)
    InvoiceConversation.where(invoice_id: invoice.id, is_primary: true).exists?
  end

  def clock_outbound_only!(invoice_ids, counts)
    return if invoice_ids.empty?

    Invoice.where(id: invoice_ids.to_a, organization_id: organization.id).find_each do |invoice|
      next if %w[paid voided partially_paid promised disputed paid_unconfirmed broken_promise].include?(invoice.current_ar_status)

      directions = Message.joins(conversation: :invoice_conversations)
        .where(invoice_conversations: { invoice_id: invoice.id })
        .pluck(:direction)
      next if directions.empty?
      next unless directions.all? { |direction| direction == "user_to_client" }

      clock_status = invoice.due_date < Date.current ? "overdue" : "invoiced"
      previous = invoice.current_ar_status
      invoice.update!(current_ar_status: clock_status, needs_reply: false)
      next if previous == clock_status

      invoice.invoice_state_transitions.create!(
        from_status: previous,
        to_status: clock_status,
        trigger_source: "clock_cron",
        created_at: Time.current
      )
      counts[:outbound_clocked] += 1
    end
  end

  def enqueue_inbound_eval!(invoice_ids, counts = nil)
    ids = inbound_invoice_ids(invoice_ids)
    ids.each { |id| Email::EvaluateInvoiceStateJob.perform_later(id) }
    counts[:ai_queued] += ids.size if counts
  end

  def inbound_invoice_ids(invoice_ids)
    return [] if invoice_ids.blank?

    Invoice.where(id: invoice_ids.to_a, organization_id: organization.id)
      .joins(invoice_conversations: { conversation: :messages })
      .where(messages: { direction: "client_to_user" })
      .distinct
      .pluck(:id)
  end

  def match_invoice?(invoice, message, client_invoices)
    match_token?(invoice, message) || match_number?(invoice, message) || match_exclusive_amount?(invoice, message, client_invoices)
  end

  def match_token?(invoice, message)
    token = invoice.pay_link_token.to_s.strip
    return false if token.blank?

    haystack = "#{message[:subject]} #{message[:raw_body]} #{message[:clean_body]}"
    haystack.downcase.include?(token.downcase)
  end

  def match_number?(invoice, message)
    number = invoice.invoice_number.to_s.strip
    return false if number.blank?

    haystack = "#{message[:subject]}\n#{message[:clean_body]}"
    return true if haystack.match?(/\b#{Regexp.escape(number)}\b/i)

    digits = number[/\d{3,}\z/]
    return false if digits.blank?

    haystack.match?(/\b#{Regexp.escape(digits)}\b/)
  end

  def match_amount?(invoice, message)
    amounts = quoted_amounts("#{message[:subject]} #{message[:clean_body]}")
    amounts.include?(invoice.total_amount.to_d)
  end

  def match_exclusive_amount?(invoice, message, client_invoices)
    amounts = quoted_amounts("#{message[:subject]} #{message[:clean_body]}")
    return false if amounts.empty?

    amounts.any? do |amount|
      hits = client_invoices.select { |row| row.total_amount.to_d == amount }
      hits.size == 1 && hits.first.id == invoice.id
    end
  end

  def quoted_amounts(text)
    text.to_s.scan(AMOUNT_PATTERN).filter_map do |whole, cents|
      normalized = whole.to_s.delete(",")
      next if normalized.blank?

      BigDecimal("#{normalized}.#{cents.presence || '00'}")
    end.uniq
  end

  def message_for_client?(message, client_row)
    emails = contact_emails([ client_row ]).to_set
    participants = ([ message[:from] ] + message[:to] + message[:cc]).map { |value| normalize_email(value) }.compact
    return true if participants.any? { |email| emails.include?(email) }

    domain = client_row.domain.to_s.downcase.presence
    return false if domain.blank?

    participants.any? { |email| email.end_with?("@#{domain}") }
  end

  def contact_emails(clients)
    clients.flat_map do |client_row|
      [ client_row.primary_email ] + Array(client_row.associated_emails) +
        client_row.invoices.flat_map { |row| Array(row.cc_emails) + Array(row.bcc_emails) }
    end.map { |email| normalize_email(email) }.compact.uniq
  end

  def normalize_message(payload)
    return if payload.blank?

    from = attendee_emails(payload["from_attendee"] || payload["from_attendees"] || payload["from"]).first
    to = attendee_emails(payload["to_attendees"] || payload["to"])
    cc = attendee_emails(payload["cc_attendees"] || payload["cc"])
    sent_at = parse_time(payload["date"] || payload["sent_at"])
    raw = payload["body_plain"].presence || payload["body"].to_s
    thread_id = payload["thread_id"].presence || payload["id"].to_s
    id = payload["id"].presence || payload["provider_id"].presence || payload["email_id"].presence
    return if id.blank? || from.blank? || sent_at.blank?

    {
      id: id.to_s,
      thread_id: thread_id.to_s,
      subject: payload["subject"].to_s,
      from: from,
      to: to,
      cc: cc,
      sent_at: sent_at,
      raw_body: raw,
      clean_body: sanitize_body(raw)
    }
  end

  def attendee_emails(value)
    entries = case value
    when Hash then [ value ]
    when nil then []
    else Array(value)
    end
    entries.filter_map do |entry|
      email = if entry.is_a?(Hash)
        entry["identifier"] || entry["email"] || entry[:identifier] || entry[:email]
      else
        entry
      end
      normalize_email(email)
    end
  end

  def direction_for(message, owner_email)
    from = normalize_email(message[:from])
    if owner_email.present? && from == owner_email
      "user_to_client"
    else
      "client_to_user"
    end
  end

  def sanitize_body(raw)
    text = raw.to_s.gsub(/<style[^>]*>.*?<\/style>/mi, " ")
    text = text.gsub(/<[^>]+>/, " ")
    text = CGI.unescapeHTML(text)
    text = text.gsub(/\r\n?/, "\n")
    text = text.split(/\n(?:-- \n|--\s*$)/, 2).first.to_s
    text = text.split(/\nOn .+ wrote:\s*\n/).first.to_s
    text = text.gsub(/^>.*\n?/, "")
    text.gsub(/[ \t]+/, " ").gsub(/\n{3,}/, "\n\n").strip
  end

  def parse_time(value)
    return if value.blank?
    return value if value.acts_like?(:time)

    Time.iso8601(value.to_s)
  rescue ArgumentError
    Time.zone.parse(value.to_s)
  end

  def normalize_email(value)
    email = value.to_s.strip.downcase
    email.presence
  end
end
