# frozen_string_literal: true

require "cgi"
require "set"

# Shared Home/Split persist + A/B/C match predicates for mailbox historical match
# and per-invoice fallback. Not an interactor.
module Email::MailboxThreadPersistence
  AMOUNT_PATTERN = /(?:usd|us\$|\$)?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?/i
  CURRENCY_AMOUNT_PATTERN = /(?:usd|us\$|\$)\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?/i

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
    direction = direction_for(message, owner_email)
    record = conversation.messages.find_by(external_message_id: message[:id])
    record ||= conversation.messages.find_by(
      sent_at: message[:sent_at],
      from_address: message[:from],
      direction: direction
    )
    record ||= conversation.messages.new(external_message_id: message[:id])
    record.external_message_id = message[:id] if record.external_message_id.blank?
    record.direction = direction
    record.from_address = message[:from]
    record.to_addresses = message[:to]
    record.cc_addresses = message[:cc]
    record.sent_at = message[:sent_at]
    record.clean_body = message[:clean_body].to_s.delete("\u0000")
    record.automatic = true if automatic_message?(message)
    record.is_anchor = true if anchor || record.is_anchor?
    record.created_at ||= Time.current
    raise_string_error(record.errors.full_messages.to_sentence) unless record.save
    collapse_duplicate_messages!(conversation, record)
  end

  def collapse_duplicate_messages!(conversation, kept)
    conversation.messages.where(
      sent_at: kept.sent_at,
      from_address: kept.from_address,
      direction: kept.direction
    ).where.not(id: kept.id).find_each(&:destroy!)
  end

  def invoice_has_home_thread?(invoice)
    InvoiceConversation.where(invoice_id: invoice.id, is_primary: true).exists?
  end

  def clock_outbound_only!(invoice_ids, counts)
    return if invoice_ids.empty?

    Invoice.where(id: invoice_ids.to_a, organization_id: organization.id).find_each do |invoice|
      next if invoice.books_closed?

      directions = Message.joins(conversation: :invoice_conversations)
        .where(invoice_conversations: { invoice_id: invoice.id })
        .pluck(:direction)
      next if directions.empty?
      next unless directions.all? { |direction| direction == "user_to_client" }

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

  def link_clustered_threads!(mailbox, client_row, invoices, messages, counts)
    owner = normalize_email(mailbox.account_name)
    matched_invoice_ids = Set.new
    matched_thread_ids = Set.new
    candidates = messages.select { |message| message_for_client?(message, client_row) }

    linked = Hash.new { |hash, key| hash[key] = Set.new }
    candidates.group_by { |message| message[:thread_id] }.each do |thread_id, thread_messages|
      targets = pass_one_invoices(thread_messages, invoices)
      if targets.empty? && client_inbound?(thread_messages, owner)
        next if automatic_inbound_only?(thread_messages, owner)
        next unless invoice_payment_intent?(thread_messages)

        targets = pass_two_invoices(thread_messages, invoices, candidates, owner)
      elsif targets.empty?
        targets = outbound_home_invoices(thread_messages, invoices, owner)
      end

      targets.each do |invoice|
        persist_thread!(mailbox, invoice, thread_id, messages, primary: false)
        linked[invoice.id] << thread_id
        matched_invoice_ids << invoice.id
        matched_thread_ids << thread_id
      end
    end

    assign_home_threads!(mailbox, invoices, messages, owner, linked)
    counts[:matched_invoices] += matched_invoice_ids.size
    clock_outbound_only!(matched_invoice_ids, counts)
    enqueue_inbound_eval!(matched_invoice_ids, counts)
    { invoice_ids: matched_invoice_ids, thread_ids: matched_thread_ids }
  end

  # Pass 1: number, else pay-link, else unique $ among invoices that already existed at this thread.
  def pass_one_invoices(thread_messages, invoices)
    existed = invoices_existing_at(invoices, thread_messages)

    named = existed.select { |invoice| thread_messages.any? { |message| match_number?(invoice, message) } }
    return named if named.any?

    linked = existed.select { |invoice| thread_messages.any? { |message| match_token?(invoice, message) } }
    return linked if linked.any?

    existed.select { |invoice| thread_messages.any? { |message| match_exclusive_amount?(invoice, message, existed) } }
  end

  # Pass 2: unlabeled payment → invoices that existed, had been sent, and were still open at this thread.
  def pass_two_invoices(thread_messages, invoices, mailbox_messages, owner_email)
    at = thread_sent_at(thread_messages)
    invoices.select do |invoice|
      invoice_existed_at?(invoice, at) && invoice_sent_by?(invoice, at, mailbox_messages, owner_email)
    end
  end

  def invoices_existing_at(invoices, thread_messages)
    at = thread_sent_at(thread_messages)
    invoices.select { |invoice| invoice_existed_at?(invoice, at) }
  end

  def thread_sent_at(thread_messages)
    Array(thread_messages).map { |message| message[:sent_at] }.compact.min
  end

  def invoice_existed_at?(invoice, at)
    return false if at.blank? || invoice.issue_date.blank?

    invoice.issue_date <= at.in_time_zone.to_date
  end

  def invoice_sent_by?(invoice, at, mailbox_messages, owner_email)
    return false if at.blank?

    Array(mailbox_messages).any? do |message|
      next false if message[:sent_at].blank? || message[:sent_at] > at

      identifying_owner_message?(message, invoice, owner_email)
    end || persisted_send_before?(invoice, at)
  end

  def persisted_send_before?(invoice, at)
    Message.joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: invoice.id }, direction: "user_to_client")
      .where("messages.sent_at <= ?", at)
      .exists?
  end

  def outbound_home_invoices(thread_messages, invoices, owner_email)
    return [] unless thread_messages.any? { |message| sent_by_owner?(message, owner_email) }

    invoices.select { |invoice| thread_messages.any? { |message| match_number?(invoice, message) || match_token?(invoice, message) } }
  end

  # HOME is the invoice dispatch: the thread that contains the oldest owner-sent
  # message identifying this invoice (number or pay-link token). A later owner
  # reply that quotes the number on another thread stays split. Linking is Pass 1/2;
  # this only sets is_primary after every candidate is attached.
  def assign_home_threads!(mailbox, invoices, messages, owner_email, linked)
    by_thread = messages.group_by { |message| message[:thread_id] }
    invoices.each do |invoice|
      thread_ids = linked[invoice.id]
      next if thread_ids.blank?

      scoped = thread_ids.index_with { |thread_id| Array(by_thread[thread_id]) }
      assign_home_thread!(mailbox, invoice, scoped, owner_email)
    end
  end

  def assign_home_thread!(mailbox, invoice, thread_messages_by_id, owner_email)
    chosen_id = dispatch_home_thread_id(invoice, thread_messages_by_id, owner_email)
    return if chosen_id.blank? && invoice_has_home_thread?(invoice)

    chosen_id ||= fallback_home_thread_id(thread_messages_by_id)
    return if chosen_id.blank?

    conversation = organization.conversations.find_by(
      integration_id: mailbox.id,
      external_thread_id: chosen_id.to_s
    )
    return if conversation.blank?

    set_home_thread!(invoice, conversation)
  end

  def dispatch_home_thread_id(invoice, thread_messages_by_id, owner_email)
    best_id = nil
    best_key = nil
    thread_messages_by_id.each do |thread_id, thread_messages|
      Array(thread_messages).each do |message|
        next unless identifying_owner_message?(message, invoice, owner_email)

        key = [ message[:sent_at], message[:id].to_s, thread_id.to_s ]
        next if best_key && (key <=> best_key) >= 0

        best_key = key
        best_id = thread_id
      end
    end
    best_id
  end

  def identifying_owner_message?(message, invoice, owner_email)
    sent_by_owner?(message, owner_email) && (match_number?(invoice, message) || match_token?(invoice, message))
  end

  def fallback_home_thread_id(thread_messages_by_id)
    thread_messages_by_id.min_by do |thread_id, thread_messages|
      first_at = Array(thread_messages).map { |message| message[:sent_at] }.compact.min || Time.zone.at(0)
      [ first_at, thread_id.to_s ]
    end&.first
  end

  def set_home_thread!(invoice, conversation)
    InvoiceConversation.where(invoice_id: invoice.id).find_each do |link|
      desired = link.conversation_id == conversation.id
      next if link.is_primary? == desired

      link.is_primary = desired
      raise_string_error(link.errors.full_messages.to_sentence) unless link.save
    end
    invoice.invoice_conversations.reset
  end

  def client_inbound?(thread_messages, owner_email)
    thread_messages.any? { |message| direction_for(message, owner_email) == "client_to_user" }
  end

  def sent_by_owner?(message, owner_email)
    return true if owner_email.blank?

    normalize_email(message[:from]) == owner_email
  end

  def automatic_inbound_only?(thread_messages, owner_email)
    inbound = thread_messages.select { |message| direction_for(message, owner_email) == "client_to_user" }
    inbound.any? && inbound.all? { |message| automatic_reply?(message) }
  end

  def automatic_reply?(message)
    automatic_message?(message)
  end

  def automatic_message?(message)
    return true if message[:automatic]
    return true if bounce_from?(message)
    return true if noreply_from?(message)

    subject = message[:subject].to_s
    return true if subject.match?(/\A\s*(automatic reply|auto[- ]reply|out of office|ooo:)/i)

    headers = message[:headers].is_a?(Hash) ? message[:headers] : {}
    auto = headers["auto-submitted"].to_s.presence || headers["Auto-Submitted"].to_s
    return true if auto.present? && !auto.match?(/\Ano\z/i)
    return true if headers["x-autoreply"].present? || headers["X-Autoreply"].present?
    return true if headers["x-autorespond"].present? || headers["X-Autorespond"].present?

    false
  end

  def bounce_from?(message)
    message[:from].to_s.match?(/mailer-daemon|postmaster/i) ||
      message[:subject].to_s.match?(/delivery status|undeliverable|returned mail/i)
  end

  def noreply_from?(message)
    local = message[:from].to_s.split("@", 2).first.to_s.downcase
    local.match?(/\A(no[-_]?reply|do[-_]?not[-_]?reply|noreply|notifications?|newsletter|mailer|digest|updates?)\z/)
  end

  def invoice_payment_intent?(thread_messages)
    llm = payment_llm
    return false if llm.blank?

    haystack = Array(thread_messages).map { |message| [ message[:subject], message[:clean_body] ].compact.join("\n") }.join("\n\n")
    result = Email::ClassifyPaymentIntent.execute(
      subject: Array(thread_messages).map { |message| message[:subject] }.find(&:present?).to_s,
      body: haystack,
      client: llm
    )
    result.success? && result.data[:intent].to_s == "invoice_payment"
  end

  def payment_llm
    @llm
  end

  def match_token?(invoice, message)
    Invoices::PayLink.match?(invoice.pay_link_token, match_haystack(message))
  end

  def match_number?(invoice, message)
    number = invoice.invoice_number.to_s.strip
    return false if number.blank?

    prose = match_prose_haystack(message)
    return true if number_hit?(prose, number)
    return true if number.match?(/[A-Za-z]/) && number_hit?(match_haystack(message), number)

    digits = number[/\d{3,}\z/]
    return false if digits.blank? || digits == number

    number_hit?(prose, digits)
  end

  def number_hit?(haystack, token)
    haystack.match?(/(?<![A-Za-z0-9])#{Regexp.escape(token)}(?![A-Za-z0-9])/i)
  end

  def match_haystack(message)
    raw = message[:raw_body].to_s
    [
      match_prose_haystack(message),
      raw,
      Invoices::PayLink.urls_in(raw)
    ].compact.join("\n")
  end

  def match_prose_haystack(message)
    [
      message[:subject],
      message[:clean_body],
      Array(message[:attachment_names]).join(" ")
    ].compact.join("\n")
  end

  def match_amount?(invoice, message)
    amounts = quoted_amounts(match_prose_haystack(message), currency_required: true)
    amounts.include?(invoice.total_amount.to_d)
  end

  def match_exclusive_amount?(invoice, message, client_invoices)
    amounts = quoted_amounts(match_prose_haystack(message), currency_required: true)
    return false if amounts.empty?

    amounts.any? do |amount|
      hits = client_invoices.select { |row| row.total_amount.to_d == amount }
      hits.size == 1 && hits.first.id == invoice.id
    end
  end

  def quoted_amounts(text, currency_required: false)
    pattern = currency_required ? CURRENCY_AMOUNT_PATTERN : AMOUNT_PATTERN
    text.to_s.scan(pattern).filter_map do |whole, cents|
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
    owner = owner_mailbox_emails
    clients.flat_map do |client_row|
      [ client_row.primary_email ] + Array(client_row.associated_emails) +
        client_row.invoices.flat_map { |row| Array(row.cc_emails) + Array(row.bcc_emails) }
    end.map { |email| normalize_email(email) }.compact.uniq.reject { |email| owner.include?(email) }
  end

  def owner_mailbox_emails
    emails = organization.integrations.mailbox.filter_map { |row| normalize_email(row.account_name) }
    emails.concat(organization.users.filter_map { |row| normalize_email(row.email) }) if organization.respond_to?(:users)
    emails.to_set
  end

  def normalize_message(payload)
    return if payload.blank?

    from = attendee_emails(payload["from_attendee"] || payload["from_attendees"] || payload["from"]).first
    to = attendee_emails(payload["to_attendees"] || payload["to"])
    cc = attendee_emails(payload["cc_attendees"] || payload["cc"])
    sent_at = parse_time(payload["date"] || payload["sent_at"])
    raw = payload["body_plain"].presence || payload["body"].to_s
    thread_id = payload["thread_id"].presence || payload["provider_id"].presence || payload["id"].to_s
    id = stable_message_id(payload)
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
      clean_body: sanitize_body(raw),
      attachment_names: attachment_names(payload),
      headers: payload["headers"].is_a?(Hash) ? payload["headers"] : {},
      automatic: payload["is_auto_reply"] == true || payload["auto_reply"] == true
    }
  end

  def stable_message_id(payload)
    rfc = payload["message_id"].to_s.gsub(/[<>]/, "").presence
    payload["provider_id"].presence || rfc || payload["id"].presence || payload["email_id"].presence
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

  def attachment_names(payload)
    Array(payload["attachments"]).filter_map do |attachment|
      next unless attachment.is_a?(Hash)

      attachment["name"].presence || attachment["filename"].presence || attachment["id"]
    end.map(&:to_s)
  end

  def sanitize_body(raw)
    text = raw.to_s.delete("\u0000")
    text = text.gsub(/<style[^>]*>.*?<\/style>/mi, " ")
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
