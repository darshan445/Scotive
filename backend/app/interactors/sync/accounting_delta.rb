# frozen_string_literal: true

# Sync::AccountingDelta Interactor
# Purpose: QBO/Xero invoices updated after last_synced_at. Same books upsert as import/webhooks.
# Methods:
# - execute

class Sync::AccountingDelta
  include ExecuteMethodHelper
  include LogHelper
  include Quickbooks::BooksPersistence
  include Quickbooks::InvoiceLinkFetch
  include Quickbooks::TokenRefresh

  LOOKBACK = 2.hours

  def self.execute(organization:, client: Quickbooks::QuickbookClient.new, xero_client: Xero::XeroClient.new)
    new(organization: organization, client: client, xero_client: xero_client).execute
  end

  def initialize(organization:, client:, xero_client: Xero::XeroClient.new)
    @organization = organization
    @client = client
    @xero_client = xero_client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      if integration.blank? && xero_integration.blank?
        { skipped: "not_connected", created: 0, updated: 0, paid: 0 }
      else
        merge_provider_counts(qbo_counts, xero_counts)
      end
    end
  end

  private

  attr_reader :organization, :client, :xero_client

  def integration
    @integration ||= organization.integrations.accounting.connected.find_by(provider: "qbo")
  end

  def xero_integration
    @xero_integration ||= organization.integrations.accounting.connected.find_by(provider: "xero")
  end

  def qbo_counts
    integration.present? ? sync_updated_invoices! : empty_counts
  end

  def xero_counts
    if xero_integration.blank?
      empty_counts
    else
      validate_result(Xero::SyncDelta.execute(organization: organization, client: xero_client)).data
    end
  end

  def empty_counts
    { created: 0, updated: 0, merged: 0, fetched: 0, paid: 0, skipped: nil }
  end

  def merge_provider_counts(left, right)
    {
      fetched: left[:fetched].to_i + right[:fetched].to_i,
      created: left[:created].to_i + right[:created].to_i,
      updated: left[:updated].to_i + right[:updated].to_i,
      merged: left[:merged].to_i + right[:merged].to_i,
      paid: left[:paid].to_i + right[:paid].to_i,
      skipped: nil
    }
  end

  def sync_updated_invoices!
    access_token = ensure_fresh_token!(integration)
    since = integration.last_synced_at.presence || LOOKBACK.ago
    invoices = attach_invoice_links!(
      integration,
      access_token,
      client.query_invoices_updated_since(
        realm_id: integration.external_account_id,
        access_token: access_token,
        since: since
      )
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
      .books_open
      .left_outer_joins(:invoice_conversations)
      .where(invoice_conversations: { invoice_id: nil })
      .find_each { |invoice| Email::FindInvoiceThreadJob.perform_later(invoice.id) }
  end

  def paid_count(payloads)
    payloads.count { |payload| BigDecimal(payload["Balance"].to_s) <= 0 }
  end
end
