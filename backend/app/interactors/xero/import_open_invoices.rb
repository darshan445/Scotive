# frozen_string_literal: true

# Xero::ImportOpenInvoices Interactor
# Purpose: Pull 365 days of open Xero ACCREC invoices, upsert only those clients, persist last_synced_at.
# Methods:
# - execute

class Xero::ImportOpenInvoices
  include ExecuteMethodHelper
  include LogHelper
  include Xero::BooksSync

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

      integration = organization.integrations.accounting.connected.find_by(provider: "xero")
      raise_string_error("Xero is not connected") if integration.blank?
      raise_string_error("Xero organisation id is missing") if integration.external_account_id.blank?

      access_token = ensure_fresh_token!(integration)
      invoices = attach_invoice_links!(integration, access_token, fetch_open_invoices(integration, access_token))
      contacts = contacts_by_id_from(access_token, invoices)
      counts = persist_xero_books!(integration, invoices, contacts)
      integration.update!(last_synced_at: Time.current)

      { counts: counts }
    end
  end

  private

  attr_reader :organization, :client

  def integration
    @integration ||= organization.integrations.accounting.connected.find_by(provider: "xero")
  end

  def ensure_fresh_token!(record)
    super
  rescue Faraday::Error
    raise_string_error("Xero authorization expired — reconnect Xero")
  end

  def fetch_open_invoices(record, access_token)
    client.query_open_invoices(
      tenant_id: record.external_account_id,
      access_token: access_token,
      since_date: 365.days.ago.to_date.iso8601
    )
  rescue Faraday::Error => e
    mark_reauth!(record) if xero_grant_error?(e)
    raise_string_error("Xero invoice import failed: #{e.message}")
  end
end
