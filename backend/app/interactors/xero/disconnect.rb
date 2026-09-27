# frozen_string_literal: true

# Xero::Disconnect Interactor
# Purpose: Revoke the Xero connection and mark the integration disconnected.
# Methods:
# - execute

class Xero::Disconnect
  include ExecuteMethodHelper
  include LogHelper

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

      integration = organization.integrations.accounting.find_by(provider: "xero")
      raise_string_error("Xero is not connected") if integration.blank?

      revoke_remote(integration)
      integration.update!(
        connection_status: "disconnected",
        access_token: nil,
        refresh_token: nil,
        token_expires_at: nil,
        webhook_subscription_id: nil
      )
      { disconnected: true }
    end
  end

  private

  attr_reader :organization, :client

  def revoke_remote(integration)
    token = integration.access_token
    refresh = integration.refresh_token
    connection_id = integration.webhook_subscription_id
    if token.present? && connection_id.present?
      client.delete_connection(access_token: token, connection_id: connection_id)
    elsif token.present?
      disconnect_by_tenant(token, integration.external_account_id)
    end
    client.revoke_token(refresh.presence || token) if refresh.present? || token.present?
  rescue Faraday::Error => e
    Rails.logger.warn("Xero revoke failed: #{e.message}")
  rescue ActiveRecord::Encryption::Errors::Decryption
    Rails.logger.warn("Xero tokens could not be decrypted during disconnect")
  end

  def disconnect_by_tenant(access_token, tenant_id)
    return if tenant_id.blank?

    rows = client.list_connections(access_token: access_token)
    match = rows.find { |row| row["tenantId"].to_s == tenant_id.to_s }
    return if match.blank?

    client.delete_connection(access_token: access_token, connection_id: match["id"])
  end
end
