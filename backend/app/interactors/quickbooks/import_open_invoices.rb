# frozen_string_literal: true

# Quickbooks::ImportOpenInvoices Interactor
# Purpose: Pull 365 days of open QBO invoices, upsert only those clients, persist last_synced_at.
# Methods:
# - execute

class Quickbooks::ImportOpenInvoices
  include ExecuteMethodHelper
  include LogHelper
  include Quickbooks::BooksPersistence

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

      integration = organization.integrations.accounting.connected.find_by(provider: "qbo")
      raise_string_error("QuickBooks is not connected") if integration.blank?
      raise_string_error("QuickBooks company id is missing") if integration.external_account_id.blank?

      access_token = ensure_fresh_token!(integration)
      invoices = fetch_open_invoices(integration, access_token)
      customers_by_id = fetch_customers(integration, access_token, invoices)
      counts = persist_books!(integration, invoices, customers_by_id)
      integration.update!(last_synced_at: Time.current)

      { counts: counts }
    end
  end

  private

  attr_reader :organization, :client

  def ensure_fresh_token!(integration)
    token = integration.access_token
    needs_refresh = integration.refresh_token.present? &&
      (integration.token_expires_at.blank? || integration.token_expires_at <= 10.minutes.from_now)

    if needs_refresh
      tokens = client.refresh_access_token(refresh_token: integration.refresh_token)
      token = tokens["access_token"] || tokens[:access_token]
      refresh = tokens["refresh_token"] || tokens[:refresh_token]
      expires_in = (tokens["expires_in"] || tokens[:expires_in]).to_i
      raise_string_error("QuickBooks did not return an access token") if token.blank?

      integration.update!(
        access_token: token,
        refresh_token: refresh.presence || integration.refresh_token,
        token_expires_at: expires_in.positive? ? Time.current + expires_in.seconds : integration.token_expires_at
      )
    end

    raise_string_error("QuickBooks access token is missing") if token.blank?
    token
  rescue Faraday::Error => e
    mark_reauth!(integration) if e.message.match?(/invalid_grant|401/)
    raise_string_error("QuickBooks authorization expired — reconnect QuickBooks")
  end

  def fetch_open_invoices(integration, access_token)
    client.query_open_invoices(
      realm_id: integration.external_account_id,
      access_token: access_token,
      since_date: 365.days.ago.to_date.iso8601
    )
  rescue Faraday::Error => e
    mark_reauth!(integration) if e.message.match?(/invalid_grant|401/)
    raise_string_error("QuickBooks invoice import failed")
  end

  def fetch_customers(integration, access_token, invoices)
    ids = invoices.filter_map { |invoice| invoice.dig("CustomerRef", "value").presence }.uniq
    return {} if ids.empty?

    client.query_customers(
      realm_id: integration.external_account_id,
      access_token: access_token,
      ids: ids
    ).index_by { |row| row["Id"].to_s }
  rescue Faraday::Error
    raise_string_error("QuickBooks customer import failed")
  end

  def mark_reauth!(integration)
    integration.update!(connection_status: "reauth_required")
  end
end
