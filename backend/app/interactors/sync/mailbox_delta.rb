# frozen_string_literal: true

# Sync::MailboxDelta Interactor
# Purpose: Unipile envelopes since last_synced_at. No historical re-scan.
# Methods:
# - execute

class Sync::MailboxDelta
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  PAGE_SIZE = 100
  MAX_PAGES = 20
  LOOKBACK = 2.hours

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

      mailboxes = organization.integrations.mailbox.connected.where.not(external_account_id: [ nil, "" ]).to_a
      if mailboxes.empty?
        { skipped: "no_connection", fetched: 0, persisted: 0, discarded: 0 }
      else
        totals = { skipped: nil, fetched: 0, persisted: 0, discarded: 0 }
        mailboxes.each { |mailbox| merge_counts!(totals, sync_mailbox!(mailbox)) }
        totals
      end
    end
  end

  private

  attr_reader :organization, :client

  def sync_mailbox!(mailbox)
    since = mailbox.last_synced_at.presence || LOOKBACK.ago
    items = fetch_since(mailbox, since)
    counts = { fetched: items.size, persisted: 0, discarded: 0 }
    items.each do |payload|
      next unless payload.is_a?(Hash)

      message = normalize_message(payload.stringify_keys)
      if message.blank? || already_persisted?(mailbox, message[:id])
        counts[:discarded] += 1
        next
      end

      outcome = validate_result(Email::RouteInboundMessage.execute(
        organization: organization,
        mailbox: mailbox,
        message: message
      )).data
      if outcome[:discarded]
        counts[:discarded] += 1
      else
        counts[:persisted] += 1
      end
    end
    mailbox.update!(
      last_synced_at: Time.current,
      sync_cursor: newest_id(items) || mailbox.sync_cursor
    )
    counts
  rescue Faraday::Error
    raise_string_error("Mailbox delta failed")
  end

  def fetch_since(mailbox, since)
    items = []
    cursor = nil
    pages = 0
    loop do
      pages += 1
      body = client.list_emails(
        account_id: mailbox.external_account_id,
        after: since.utc.iso8601(3),
        cursor: cursor,
        limit: PAGE_SIZE
      )
      page = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
      items.concat(page)
      cursor = body.is_a?(Hash) ? (body["cursor"] || body["next_cursor"]) : nil
      break if page.size < PAGE_SIZE || cursor.blank? || pages >= MAX_PAGES
    end
    items
  end

  def already_persisted?(mailbox, external_id)
    Message.joins(:conversation).where(
      conversations: { organization_id: organization.id, integration_id: mailbox.id },
      external_message_id: external_id
    ).exists?
  end

  def newest_id(items)
    items.filter_map { |row| row["id"].presence || row["email_id"].presence || row["provider_id"].presence }.last
  end

  def merge_counts!(totals, counts)
    totals[:fetched] += counts[:fetched]
    totals[:persisted] += counts[:persisted]
    totals[:discarded] += counts[:discarded]
  end
end
