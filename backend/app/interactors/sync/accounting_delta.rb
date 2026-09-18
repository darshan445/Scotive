# frozen_string_literal: true

# Sync::AccountingDelta Interactor
# Purpose: QBO invoices updated after last_synced_at. Same books upsert as import/webhooks.
# Methods:
# - execute

class Sync::AccountingDelta
  include ExecuteMethodHelper
  include LogHelper
  include Quickbooks::BooksPersistence
  include Quickbooks::TokenRefresh

  LOOKBACK = 2.hours

  def self.execute(organization:, client: Quickbooks::QuickbookClient.new)
    new(organization: organization, client: client).execute
  end

  def initialize(organization:, client:)
    @organization = organization
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      if integration.blank?
        { skipped: "not_connected", created: 0, updated: 0, paid: 0 }
      else
        sync_updated_invoices!
      end
    end
  end

  private

  attr_reader :organization, :client

  def integration
    @integration ||= organization.integrations.accounting.connected.find_by(provider: "qbo")
  end

  def sync_updated_invoices!
    access_token = ensure_fresh_token!(integration)
    since = integration.last_synced_at.presence || LOOKBACK.ago
    invoices = client.query_invoices_updated_since(
      realm_id: integration.external_account_id,
      access_token: access_token,
      since: since
    )
    customers_by_id = fetch_customers(access_token, invoices)
    counts = persist_books!(integration, invoices, customers_by_id, trigger_source: "books_sync")
    enqueue_unmatched!(invoices)
    integration.update!(last_synced_at: Time.current)
    counts.merge(paid: paid_count(invoices), skipped: nil)
  rescue Faraday::Error => e
    mark_reauth!(integration) if qbo_grant_error?(e)
    raise_string_error("QuickBooks accounting delta failed")
  end

  def fetch_customers(access_token, invoices)
    ids = invoices.filter_map { |invoice| invoice.dig("CustomerRef", "value").presence }.uniq
    return {} if ids.empty?

    client.query_customers(
      realm_id: integration.external_account_id,
      access_token: access_token,
      ids: ids
    ).index_by { |row| row["Id"].to_s }
  rescue Faraday::Error
    {}
  end

  def enqueue_unmatched!(payloads)
    ids = payloads.filter_map { |payload| payload["Id"].to_s.presence }
    return if ids.empty?

    organization.invoices
      .where(integration_id: integration.id, external_id: ids)
      .where.not(current_ar_status: %w[paid voided])
      .left_outer_joins(:invoice_conversations)
      .where(invoice_conversations: { invoice_id: nil })
      .find_each { |invoice| Email::FindInvoiceThreadJob.perform_later(invoice.id) }
  end

  def paid_count(payloads)
    payloads.count { |payload| BigDecimal(payload["Balance"].to_s) <= 0 }
  end
end
