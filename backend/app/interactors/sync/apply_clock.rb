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

      { wait_expired: expire_waits! }
    end
  end

  private

  attr_reader :organization, :client

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

  # :ok — books refreshed (or local-only). :unavailable — do not expire on a stale unpaid.
  def reconcile_from_quickbooks!(invoice)
    integration = invoice.integration
    return :ok unless live_qbo?(integration, invoice)

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
  rescue Faraday::Error => e
    if e.message.to_s.match?(/404/)
      Invoice.transaction do
        void_local_invoice!(organization.invoices.lock.find(invoice.id))
      end
      return :ok
    end

    mark_reauth!(integration) if qbo_grant_error?(e)
    :unavailable
  rescue StandardError
    :unavailable
  end

  def live_qbo?(integration, invoice)
    integration&.provider == "qbo" &&
      integration.connection_status == "connected" &&
      integration.access_token.present? &&
      invoice.external_id.present? &&
      !invoice.external_id.to_s.start_with?("demo-")
  end
end
