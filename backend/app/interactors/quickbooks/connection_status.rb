# frozen_string_literal: true

# Quickbooks::ConnectionStatus Interactor
# Purpose: Serialize the org's QBO integration for the frontend connect UI.
# Methods:
# - execute

class Quickbooks::ConnectionStatus
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      integration = organization.integrations.accounting.find_by(provider: "qbo")
      connected = integration&.connected? || false
      {
        connected: connected,
        status: integration&.connection_status || "disconnected",
        realm_id: integration&.external_account_id,
        company_name: integration&.account_name,
        env: ENV.fetch("QBO_ENV", "sandbox"),
        last_invoice_import_at: connected ? integration.last_synced_at : nil,
        import_progress: import_progress(integration)
      }
    end
  end

  private

  attr_reader :organization

  def import_progress(integration)
    if integration&.connected? && integration.last_synced_at.present?
      { "status" => "complete" }
    else
      { "status" => "idle" }
    end
  end
end
