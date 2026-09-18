# frozen_string_literal: true

# Email::FindInvoiceThread Interactor
# Purpose: AR Step 4 — bounded A→E mailbox fallback for one missed invoice.
# Methods:
# - execute

class Email::FindInvoiceThread
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  PAGE_SIZE = 100
  MAX_PAGES = 5

  def self.execute(invoice:, client: Email::EmailClient.new)
    new(invoice: invoice, client: client).execute
  end

  def initialize(invoice:, client:)
    @invoice = invoice
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invoice is required") if invoice.blank?

      if skip_search?
        { matched: linked?, query: nil, unmatched: invoice.current_ar_status == "unmatched" }
      else
        query = search_mailboxes!
        mark_unmatched! if query.blank? && !linked?
        { matched: query.present?, query: query, unmatched: invoice.current_ar_status == "unmatched" }
      end
    end
  end

  private

  attr_reader :invoice, :client

  def organization
    invoice.organization
  end

  def skip_search?
    linked? || terminal? || mailboxes.empty?
  end

  def linked?
    invoice.invoice_conversations.exists?
  end

  def terminal?
    invoice.balance_remaining.to_d <= 0 || %w[paid voided].include?(invoice.current_ar_status)
  end

  def mailboxes
    @mailboxes ||= organization.integrations.mailbox.connected.where.not(external_account_id: [ nil, "" ]).to_a
  end

  def search_mailboxes!
    found = nil
    mailboxes.each do |mailbox|
      found = search_mailbox!(mailbox)
      break if found.present?
    end
    found
  end

  def search_mailbox!(mailbox)
    hit = query_a!(mailbox)
    hit = query_b!(mailbox) if hit.blank?
    hit = query_c!(mailbox) if hit.blank?
    hit = query_d!(mailbox) if hit.blank?
    hit
  end

  def query_a!(mailbox)
    token = invoice.pay_link_token.to_s.strip
    return if token.blank?

    messages = fetch_query(mailbox, gmail: gmail_token_query(token), outlook: { search: token })
    matched = messages.select { |message| match_token?(invoice, message) }
    persist_hit!(mailbox, messages, matched, "A")
  end

  def query_b!(mailbox)
    number = invoice.invoice_number.to_s.strip
    contacts = contact_clause
    return if number.blank? || contacts.blank?

    messages = fetch_query(
      mailbox,
      gmail: "#{contacts} #{gmail_quote(number)} after:#{gmail_after}",
      outlook: { search: number }
    )
    matched = messages.select { |message| message_for_client?(message, invoice.client) && match_number?(invoice, message) }
    persist_hit!(mailbox, messages, matched, "B")
  end

  def query_c!(mailbox)
    token = invoice.pay_link_token.to_s.strip
    number = invoice.invoice_number.to_s.strip
    terms = [ token, number ].filter_map { |value| gmail_quote(value) if value.present? }
    owner = normalize_email(mailbox.account_name)
    return if terms.empty? || (mailbox.provider != "gmail" && owner.blank?)

    messages = fetch_query(
      mailbox,
      gmail: "from:me (#{terms.join(' OR ')}) after:#{gmail_after}",
      outlook: { from: owner, after: after_iso }
    )
    matched = messages.select { |message| sent_by_owner?(message, owner) && (match_token?(invoice, message) || match_number?(invoice, message)) }
    persist_hit!(mailbox, messages, matched, "C")
  end

  def query_d!(mailbox)
    contacts = contact_clause
    return if contacts.blank? || invoice.total_amount.blank?

    messages = fetch_query(
      mailbox,
      gmail: "#{contacts} #{gmail_quote(amount_text)} after:#{gmail_after}",
      outlook: { any_email: contact_emails([ invoice.client ]).join(","), after: after_iso }
    )
    matched = messages.select { |message| message_for_client?(message, invoice.client) && match_amount?(invoice, message) }
    persist_hit!(mailbox, messages, matched, "D")
  end

  def persist_hit!(mailbox, messages, matched, query)
    thread_ids = matched.map { |message| message[:thread_id] }.uniq
    return if thread_ids.empty?

    thread_ids.each_with_index do |thread_id, index|
      persist_thread!(
        mailbox,
        invoice,
        thread_id,
        messages,
        primary: index.zero? && !invoice_has_home_thread?(invoice)
      )
    end
    clock_outbound_only!([ invoice.id ], Hash.new(0))
    enqueue_inbound_eval!([ invoice.id ])
    remember_unknown_participants!(mailbox, matched) if query == "A"
    query
  end

  def remember_unknown_participants!(mailbox, messages)
    owner = normalize_email(mailbox.account_name)
    extras = messages.flat_map { |message| [ message[:from] ] + message[:to] + message[:cc] }
      .map { |value| normalize_email(value) }
      .compact
      .uniq
      .reject { |email| email == owner }
    return if extras.empty?

    client_row = invoice.client
    current = Array(client_row.associated_emails).map { |value| normalize_email(value) }.compact
    merged = (current + extras).uniq
    client_row.update!(associated_emails: merged) if merged != current
  end

  def mark_unmatched!
    return if invoice.current_ar_status == "unmatched" || terminal?

    previous = invoice.current_ar_status
    invoice.update!(current_ar_status: "unmatched")
    invoice.invoice_state_transitions.create!(
      from_status: previous,
      to_status: "unmatched",
      trigger_source: "mailbox_match",
      created_at: Time.current
    )
  end

  def fetch_query(mailbox, gmail:, outlook:)
    params = mailbox.provider == "gmail" ? { search: gmail, after: after_iso } : outlook
    fetch_messages(mailbox, **params)
  end

  def fetch_messages(mailbox, search: nil, any_email: nil, from: nil, after: nil)
    return [] if search.blank? && any_email.blank? && from.blank?

    items = []
    cursor = nil
    pages = 0
    loop do
      pages += 1
      body = client.list_emails(
        account_id: mailbox.external_account_id,
        after: after,
        any_email: any_email.presence,
        search: search,
        from: from,
        cursor: cursor,
        limit: PAGE_SIZE
      )
      page = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
      items.concat(page)
      cursor = body.is_a?(Hash) ? (body["cursor"] || body["next_cursor"]) : nil
      break if page.size < PAGE_SIZE || cursor.blank? || pages >= MAX_PAGES
    end
    items.filter_map { |payload| normalize_message(payload) }.select { |message| after_issue?(message) }
  rescue Faraday::Error
    raise_string_error("Mailbox search failed")
  end

  def after_issue?(message)
    message[:sent_at] >= invoice.issue_date.in_time_zone.beginning_of_day
  end

  def sent_by_owner?(message, owner)
    return true if owner.blank?

    normalize_email(message[:from]) == owner
  end

  def contact_clause
    parts = contact_emails([ invoice.client ]).flat_map { |email| [ "from:#{email}", "to:#{email}" ] }
    return if parts.empty?

    "(#{parts.join(' OR ')})"
  end

  def gmail_token_query(token)
    "#{gmail_quote(token)} after:#{gmail_after}"
  end

  def gmail_quote(value)
    %("#{value.to_s.delete('"')}")
  end

  def gmail_after
    invoice.issue_date.strftime("%Y/%m/%d")
  end

  def after_iso
    invoice.issue_date.beginning_of_day.utc.iso8601(3)
  end

  def amount_text
    format("%.2f", invoice.total_amount)
  end
end
