# frozen_string_literal: true

# Xero::SyncDelta Interactor
# Purpose: Xero invoices updated after last_synced_at. Same books upsert as import/webhooks.
# Methods:
# - execute

class Xero::SyncDelta
  include ExecuteMethodHelper
  include LogHelper
  include Xero::BooksSync

  LOOKBACK = 2.hours

  def self.execute(organization:, client: Xero::XeroClient.new)
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
    @integration ||= organization.integrations.accounting.connected.find_by(provider: "xero")
  end

  def sync_updated_invoices!
    access_token = ensure_fresh_token!(integration)
    since = integration.last_synced_at.presence || LOOKBACK.ago
    invoices = attach_invoice_links!(
      integration,
      access_token,
      client.query_invoices_updated_since(
        tenant_id: integration.external_account_id,
        access_token: access_token,
        since: since
      )
    )
    contacts = contacts_by_id_from(access_token, invoices)
    counts = persist_xero_books!(integration, invoices, contacts, trigger_source: "books_sync")
    enqueue_unmatched!(invoices)
    integration.update!(last_synced_at: Time.current)
    counts.merge(paid: paid_count(invoices), skipped: nil)
  rescue Faraday::Error => e
    mark_reauth!(integration) if xero_grant_error?(e)
    raise_string_error("Xero accounting delta failed")
  end

  def enqueue_unmatched!(payloads)
    ids = payloads.filter_map { |payload| payload["InvoiceID"].to_s.presence }
    return if ids.empty?

    organization.invoices
      .where(integration_id: integration.id, external_id: ids)
      .books_open
      .left_outer_joins(:invoice_conversations)
      .where(invoice_conversations: { invoice_id: nil })
      .find_each { |invoice| Email::FindInvoiceThreadJob.perform_later(invoice.id) }
  end

  def paid_count(payloads)
    payloads.count { |payload| BigDecimal(payload["AmountDue"].to_s) <= 0 }
  end
end
