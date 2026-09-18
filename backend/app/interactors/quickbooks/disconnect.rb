# frozen_string_literal: true

# Quickbooks::Disconnect Interactor
# Purpose: Revoke Intuit tokens and mark the QBO integration disconnected.
# Methods:
# - execute

class Quickbooks::Disconnect
  include ExecuteMethodHelper
  include LogHelper

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

      integration = organization.integrations.accounting.find_by(provider: "qbo")
      raise_string_error("QuickBooks is not connected") if integration.blank?

      token = integration.refresh_token.presence || integration.access_token
      revoke_token(token)

      integration.update!(
        connection_status: "disconnected",
        access_token: nil,
        refresh_token: nil,
        token_expires_at: nil
      )
      { disconnected: true }
    end
  end

  private

  attr_reader :organization, :client

  def revoke_token(token)
    return if token.blank?

    client.revoke_token(token)
  rescue Faraday::Error => e
    Rails.logger.warn("QBO revoke failed: #{e.message}")
  end
end
