# frozen_string_literal: true

# Email::Disconnect Interactor
# Purpose: Remove the Unipile account and mark the mailbox integration disconnected.
# Methods:
# - execute

class Email::Disconnect
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:, provider: nil, client: Email::EmailClient.new)
    new(organization: organization, provider: provider, client: client).execute
  end

  def initialize(organization:, provider:, client:)
    @organization = organization
    @provider = provider.to_s
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      scope = organization.integrations.mailbox
      integration = if mailbox_provider
        scope.find_by(provider: mailbox_provider)
      else
        scope.connected.first || scope.first
      end
      raise_string_error("Mailbox is not connected") if integration.blank?

      delete_remote_account(integration.external_account_id)
      integration.update!(
        connection_status: "disconnected",
        access_token: nil,
        refresh_token: nil,
        sync_cursor: nil,
        last_synced_at: nil
      )
      { disconnected: true, provider: integration.provider }
    end
  end

  private

  attr_reader :organization, :provider, :client

  def mailbox_provider
    case provider
    when "outlook", "microsoft" then "outlook"
    when "gmail", "google" then "gmail"
    when "" then nil
    else
      raise_string_error("Unsupported mailbox provider")
    end
  end

  def delete_remote_account(account_id)
    return if account_id.blank?

    client.delete_account(account_id)
  rescue Faraday::Error => e
    Rails.logger.warn("Unipile delete account failed: #{e.message}")
  end
end
