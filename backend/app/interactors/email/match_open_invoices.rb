# frozen_string_literal: true

require "set"

# Email::MatchOpenInvoices Interactor
# Purpose: Onboarding — one client mailbox window, Pass 1 numbers/amounts, Pass 2 AI joint link.
# Methods:
# - execute

class Email::MatchOpenInvoices
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  BATCH_SIZE = 10
  PAGE_SIZE = 100
  MAX_PAGES_PER_BATCH = 20
  HISTORY_DAYS = 365

  def self.execute(organization:, client: Email::EmailClient.new, llm: Email::LlmClient.new)
    new(organization: organization, client: client, llm: llm).execute
  end

  def initialize(organization:, client:, llm:)
    @organization = organization
    @client = client
    @llm = llm
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      qbo = organization.integrations.accounting.connected.find_by(provider: "qbo")
      raise_string_error("Import invoices before matching") if qbo&.last_synced_at.blank?

      mailboxes = organization.integrations.mailbox.connected.to_a
      raise_string_error("Connect Gmail or Outlook first") if mailboxes.empty?
      raise_string_error("Mailbox account id is missing") if mailboxes.any? { |row| row.external_account_id.blank? }

      clients = matchable_clients
      counts = empty_counts.merge(clients: clients.size, batches: mailboxes.size * batch_count(clients))
      mailboxes.each { |mailbox| match_mailbox!(mailbox, clients, counts) }
      persist_cursors!(mailboxes)
      enqueue_fallback!(counts)

      { queued: false, counts: counts, pipeline: pipeline_hash(counts, "complete") }
    end
  end

  private

  attr_reader :organization, :client, :llm

  def matchable_clients
    organization.clients.includes(invoices: :invoice_conversations).select { |row| open_invoices_for(row).any? }
  end

  def open_invoices_for(client_row)
    client_row.invoices.select(&:books_open?)
  end

  def empty_counts
    { clients: 0, batches: 0, fetched: 0, matched_invoices: 0, conversations: 0, messages: 0, outbound_clocked: 0, fallback_queued: 0, ai_queued: 0 }
  end

  def batch_count(clients)
    (clients.size / BATCH_SIZE.to_f).ceil
  end

  def match_mailbox!(mailbox, clients, counts)
    clients.each_slice(BATCH_SIZE) do |batch|
      messages = fetch_batch_messages(mailbox, batch)
      counts[:fetched] += messages.size
      persist_matches!(mailbox, batch, messages, counts)
    end
  end

  def fetch_batch_messages(mailbox, batch)
    earliest = search_after_date(batch)
    return [] if earliest.blank?

    after = earliest.beginning_of_day.utc.iso8601(3)
    emails = contact_emails(batch)
    search = mailbox.provider == "gmail" ? gmail_query(batch, earliest) : nil
    any_email = mailbox.provider == "gmail" ? nil : emails.join(",")
    return [] if search.blank? && any_email.blank?

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
        cursor: cursor,
        limit: PAGE_SIZE
      )
      page = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
      items.concat(page)
      cursor = body.is_a?(Hash) ? (body["cursor"] || body["next_cursor"]) : nil
      break if page.size < PAGE_SIZE || cursor.blank? || pages >= MAX_PAGES_PER_BATCH
    end
    items.filter_map { |payload| normalize_message(payload) }
  rescue Faraday::Error
    raise_string_error("Mailbox search failed")
  end

  def persist_matches!(mailbox, batch, messages, counts)
    batch.each do |client_row|
      invoices = open_invoices_for(client_row)
      next if invoices.empty?

      clustered = link_clustered_threads!(mailbox, client_row, invoices, messages, counts)
      recount_persisted!(mailbox, clustered[:thread_ids], counts)
    end
  end

  def recount_persisted!(mailbox, thread_ids, counts)
    return if thread_ids.blank?

    conversations = organization.conversations.where(integration_id: mailbox.id, external_thread_id: thread_ids.to_a)
    counts[:conversations] += conversations.count
    counts[:messages] += Message.where(conversation_id: conversations.select(:id)).count
  end

  def persist_cursors!(mailboxes)
    mailboxes.each do |mailbox|
      mailbox.update!(sync_cursor: head_cursor(mailbox), last_synced_at: Time.current)
    end
  end

  def head_cursor(mailbox)
    body = client.list_emails(account_id: mailbox.external_account_id, limit: 1)
    items = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
    items.dig(0, "id").presence || items.dig(0, "provider_id").presence || "empty"
  rescue Faraday::Error
    Time.current.utc.iso8601
  end

  def enqueue_fallback!(counts)
    missed = missed_invoices
    missed.each { |row| Email::FindInvoiceThreadJob.perform_later(row.id) }
    counts[:fallback_queued] = missed.size
  end

  def missed_invoices
    organization.invoices
      .books_open
      .left_outer_joins(:invoice_conversations)
      .where(invoice_conversations: { invoice_id: nil })
      .to_a
  end

  def search_after_date(clients)
    earliest = clients.flat_map { |client_row| open_invoices_for(client_row).map(&:issue_date) }.compact.min
    return if earliest.blank?

    floor = Date.current - HISTORY_DAYS
    [ earliest, floor ].max
  end

  def gmail_query(clients, earliest)
    clauses = clients.filter_map { |client_row| gmail_client_clause(client_row) }
    return if clauses.empty?

    after = earliest.strftime("%Y/%m/%d")
    "after:#{after} AND (#{clauses.join(' OR ')})"
  end

  def gmail_client_clause(client_row)
    parts = contact_emails([ client_row ]).flat_map { |email| [ "from:#{email}", "to:#{email}" ] }
    domain = client_row.domain.to_s.downcase.presence
    parts.concat([ "from:#{domain}", "to:#{domain}" ]) if domain.present?
    return if parts.empty?

    "(#{parts.join(' OR ')})"
  end

  def pipeline_hash(counts, status)
    {
      status: status,
      phase: "matching",
      examined: counts[:matched_invoices],
      total: counts[:clients]
    }
  end
end
