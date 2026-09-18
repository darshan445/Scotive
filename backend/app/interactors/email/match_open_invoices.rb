# frozen_string_literal: true

require "set"

# Email::MatchOpenInvoices Interactor
# Purpose: AR Steps 2–3 — batch mailbox search, in-memory A/B/C match, persist threads.
# Methods:
# - execute

class Email::MatchOpenInvoices
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  BATCH_SIZE = 10
  PAGE_SIZE = 100
  MAX_PAGES_PER_BATCH = 20

  def self.execute(organization:, client: Email::EmailClient.new)
    new(organization: organization, client: client).execute
  end

  def initialize(organization:, client:)
    @organization = organization
    @client = client
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

  attr_reader :organization, :client

  def matchable_clients
    organization.clients.includes(invoices: :invoice_conversations).select { |row| open_invoices_for(row).any? }
  end

  def open_invoices_for(client_row)
    client_row.invoices.select { |invoice| invoice.balance_remaining.to_d.positive? && invoice.current_ar_status != "voided" }
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
    earliest = earliest_issue_date(batch)
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
    matched_invoice_ids = Set.new
    matched_thread_ids = Set.new

    batch.each do |client_row|
      invoices = open_invoices_for(client_row)
      next if invoices.empty?

      candidates = messages.select { |message| message_for_client?(message, client_row) }
      invoices.each do |invoice|
        thread_ids = candidates.filter_map do |message|
          message[:thread_id] if match_invoice?(invoice, message, invoices)
        end.uniq
        next if thread_ids.empty?

        matched_invoice_ids << invoice.id
        thread_ids.each_with_index do |thread_id, index|
          matched_thread_ids << thread_id
          persist_thread!(
            mailbox,
            invoice,
            thread_id,
            messages,
            primary: index.zero? && !invoice_has_home_thread?(invoice)
          )
        end
      end
    end

    counts[:matched_invoices] += matched_invoice_ids.size
    clock_outbound_only!(matched_invoice_ids, counts)
    enqueue_inbound_eval!(matched_invoice_ids, counts)
    recount_persisted!(mailbox, matched_thread_ids, counts)
  end

  def recount_persisted!(mailbox, thread_ids, counts)
    return if thread_ids.empty?

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
      .where("balance_remaining > ?", 0)
      .where.not(current_ar_status: %w[paid voided])
      .left_outer_joins(:invoice_conversations)
      .where(invoice_conversations: { invoice_id: nil })
      .to_a
  end

  def earliest_issue_date(clients)
    clients.flat_map { |client_row| open_invoices_for(client_row).map(&:issue_date) }.compact.min
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
