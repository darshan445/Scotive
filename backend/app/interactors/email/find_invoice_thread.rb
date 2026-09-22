# frozen_string_literal: true

# Email::FindInvoiceThread Interactor
# Purpose: Fallback for one unmatched invoice — outbound home thread, then client Pass 1/2.
# Methods:
# - execute

class Email::FindInvoiceThread
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  PAGE_SIZE = 100
  MAX_PAGES = 5

  def self.execute(invoice:, client: Email::EmailClient.new, llm: Email::LlmClient.new)
    new(invoice: invoice, client: client, llm: llm).execute
  end

  def initialize(invoice:, client:, llm:)
    @invoice = invoice
    @client = client
    @llm = llm
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invoice is required") if invoice.blank?

      if skip_search?
        { matched: linked?, query: nil, unmatched: !linked? }
      else
        query = search_mailboxes!
        apply_clock_if_missed! if query.blank? && !linked?
        { matched: query.present? || linked?, query: query, unmatched: !linked? }
      end
    end
  end

  private

  attr_reader :invoice, :client, :llm

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
    hit = query_outbound_home!(mailbox)
    hit = query_client_cluster!(mailbox) if hit.blank?
    hit
  end

  def query_outbound_home!(mailbox)
    owner = normalize_email(mailbox.account_name)
    terms = outbound_home_terms
    return if terms.blank? || (mailbox.provider != "gmail" && owner.blank?)

    gmail_terms = terms.map { |term| gmail_quote(term) }.join(" OR ")
    messages = fetch_query(
      mailbox,
      gmail: "from:me (#{gmail_terms}) after:#{gmail_after}",
      outlook: { from: owner, after: after_iso }
    )
    matched = messages.select { |message| identifying_owner_message?(message, invoice, owner) }
    persist_hit!(mailbox, messages, matched, "home")
  end

  def outbound_home_terms
    [
      invoice.invoice_number.to_s.strip.presence,
      *Invoices::PayLink.search_terms(invoice.pay_link_token)
    ].compact.uniq
  end

  def query_client_cluster!(mailbox)
    contacts = contact_clause
    return if contacts.blank?

    messages = fetch_query(
      mailbox,
      gmail: "#{contacts} after:#{gmail_after}",
      outlook: { any_email: contact_emails([ invoice.client ]).join(","), after: after_iso }
    )
    invoices = [ invoice ] + sibling_invoices
    counts = empty_cluster_counts
    clustered = link_clustered_threads!(mailbox, invoice.client, invoices, messages, counts)
    return if clustered[:invoice_ids].exclude?(invoice.id)

    "client"
  end

  def empty_cluster_counts
    { matched_invoices: 0, outbound_clocked: 0, ai_queued: 0 }
  end

  def persist_hit!(mailbox, messages, matched, query)
    thread_ids = matched.map { |message| message[:thread_id] }.uniq
    return if thread_ids.empty?

    thread_ids.each do |thread_id|
      persist_thread!(mailbox, invoice, thread_id, messages, primary: false)
    end
    owner = normalize_email(mailbox.account_name)
    scoped = thread_ids.index_with { |thread_id| messages.select { |message| message[:thread_id] == thread_id } }
    assign_home_thread!(mailbox, invoice, scoped, owner)
    clock_outbound_only!([ invoice.id ], Hash.new(0))
    enqueue_inbound_eval!([ invoice.id ])
    query
  end

  def sibling_invoices
    invoice.client.invoices
      .where("balance_remaining > ?", 0)
      .where.not(id: invoice.id)
      .where.not(current_ar_status: %w[paid voided])
      .to_a
  end

  def apply_clock_if_missed!
    clock = invoice.due_date < Date.current ? "overdue" : "invoiced"
    previous = invoice.current_ar_status
    return if previous == clock || %w[promised broken_promise disputed paid_unconfirmed partially_paid].include?(previous)

    invoice.update!(current_ar_status: clock)
    invoice.invoice_state_transitions.create!(
      from_status: previous,
      to_status: clock,
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

  def contact_clause
    parts = contact_emails([ invoice.client ]).flat_map { |email| [ "from:#{email}", "to:#{email}" ] }
    domain = invoice.client.domain.to_s.downcase.presence
    parts.concat([ "from:#{domain}", "to:#{domain}" ]) if domain.present?
    return if parts.empty?

    "(#{parts.join(' OR ')})"
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
end
