# frozen_string_literal: true

# Sync::ApplyClock Interactor
# Purpose: wait-until date passed → ask QuickBooks, then Needs you only if still unpaid.
# Methods:
# - execute

class Sync::ApplyClock
  include ExecuteMethodHelper
  include LogHelper
  include Quickbooks::BooksPersistence
  include Quickbooks::TokenRefresh

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

      { wait_expired: expire_waits!, friendly_ended: expire_friendly_windows! }
    end
  end

  private

  attr_reader :organization, :client, :xero_client

  def expire_waits!
    count = 0
    wait_scope.find_each do |invoice|
      next if reconcile_from_quickbooks!(invoice) == :unavailable

      Invoice.transaction do
        row = organization.invoices.lock.find(invoice.id)
        next unless row.books_open? && row.chase_status == "watching" && row.wait_expired?

        apply_wait_expired!(row)
        count += 1
      end
    end
    count
  end

  def wait_scope
    organization.invoices.books_open
      .where(chase_status: "watching")
      .where("expected_pay_date < ?", Date.current)
  end

  def expire_friendly_windows!
    count = 0
    friendly_scope.find_each do |invoice|
      Invoice.transaction do
        row = organization.invoices.lock.find(invoice.id)
        next if row.chase_status != "watching"

        apply_friendly_window!(row)
        count += 1 if row.chase_status == "needs_you"
      end
    end
    count
  end

  def friendly_scope
    organization.invoices.books_open
      .where(chase_status: "watching", last_human_inbound_at: nil)
      .where("expected_pay_date IS NULL OR expected_pay_date < ?", organization.today)
  end

  # :ok — books refreshed (or local-only). :unavailable — do not expire on a stale unpaid.
  def reconcile_from_quickbooks!(invoice)
    integration = invoice.integration
    return :ok unless live_books?(integration, invoice)

    if integration.provider == "xero"
      reconcile_from_xero!(invoice, integration)
    else
      reconcile_from_qbo!(invoice, integration)
    end
  rescue Faraday::Error => e
    if e.message.to_s.match?(/404/)
      Invoice.transaction do
        void_local_invoice!(organization.invoices.lock.find(invoice.id))
      end
      return :ok
    end

    mark_reauth!(integration) if books_grant_error?(integration, e)
    :unavailable
  rescue StandardError
    :unavailable
  end

  def reconcile_from_qbo!(invoice, integration)
    access_token = ensure_fresh_token!(integration)
    payload = client.get_invoice(
      realm_id: integration.external_account_id,
      access_token: access_token,
      id: invoice.external_id
    )
    Invoice.transaction do
      upsert_invoice!(integration, invoice.client, payload, trigger_source: "books_sync")
    end
    :ok
  end

  def reconcile_from_xero!(invoice, integration)
    access_token = xero_fresh_token!(integration)
    payload = xero_client.get_invoice(
      tenant_id: integration.external_account_id,
      access_token: access_token,
      id: invoice.external_id
    )
    if Xero::InvoiceMapper.voided?(payload)
      Invoice.transaction do
        void_local_invoice!(organization.invoices.lock.find(invoice.id))
      end
    else
      mapped = Xero::InvoiceMapper.to_books_invoice(payload)
      Invoice.transaction do
        upsert_invoice!(integration, invoice.client, mapped, trigger_source: "books_sync")
      end
    end
    :ok
  end

  def xero_fresh_token!(record)
    token = record.access_token
    if record.refresh_token.present? && (record.token_expires_at.blank? || record.token_expires_at <= 10.minutes.from_now)
      tokens = xero_client.refresh_access_token(refresh_token: record.refresh_token)
      token = tokens["access_token"] || tokens[:access_token]
      refresh = tokens["refresh_token"] || tokens[:refresh_token]
      expires_in = (tokens["expires_in"] || tokens[:expires_in]).to_i
      raise_string_error("Xero did not return an access token") if token.blank?

      record.update!(
        access_token: token,
        refresh_token: refresh.presence || record.refresh_token,
        token_expires_at: expires_in.positive? ? Time.current + expires_in.seconds : record.token_expires_at
      )
    end
    raise_string_error("Xero access token is missing") if token.blank?

    token
  rescue ActiveRecord::Encryption::Errors::Decryption
    record.update!(connection_status: "reauth_required")
    raise_string_error("Xero credentials could not be decrypted — reconnect Xero")
  end

  def live_books?(integration, invoice)
    %w[qbo xero].include?(integration&.provider) &&
      integration.connection_status == "connected" &&
      integration.access_token.present? &&
      invoice.external_id.present? &&
      !invoice.external_id.to_s.start_with?("demo-")
  end

  def books_grant_error?(integration, error)
    if integration&.provider == "xero"
      error.message.to_s.match?(/invalid_grant|401|unauthorized/i)
    else
      qbo_grant_error?(error)
    end
  end
end
