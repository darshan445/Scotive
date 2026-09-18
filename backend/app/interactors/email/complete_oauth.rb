# frozen_string_literal: true

# Email::CompleteOauth Interactor
# Purpose: Persist a Gmail/Outlook integration after Unipile hosted auth succeeds.
# Methods:
# - execute

class Email::CompleteOauth
  include ExecuteMethodHelper
  include LogHelper
  include OauthStateHelper

  def self.execute(account_id:, state:, client: Email::EmailClient.new)
    new(account_id: account_id, state: state, client: client).execute
  end

  def initialize(account_id:, state:, client:)
    @account_id = account_id.to_s
    @state = state.to_s
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Missing Unipile account id") if account_id.blank?

      claims = decode_oauth_state!(state)
      organization = Organization.find_by(id: claims["organization_id"])
      raise_string_error("Organization not found") if organization.blank?

      account = fetch_account
      mailbox_provider = mailbox_provider_from(account, claims["provider"])
      email_address = mailbox_email(account)

      integration = organization.integrations.mailbox.find_or_initialize_by(provider: mailbox_provider)
      integration.assign_attributes(
        category: "mailbox",
        external_account_id: account_id,
        account_name: email_address,
        connection_status: "connected"
      )
      raise_string_error(integration.errors.full_messages.to_sentence) unless integration.save
      register_mailbox_webhook(organization)

      {
        integration_id: integration.id,
        provider: mailbox_provider,
        email: email_address
      }
    end
  end

  private

  attr_reader :account_id, :state, :client

  def fetch_account
    client.get_account(account_id)
  rescue Faraday::Error
    raise_string_error("Could not load mailbox account")
  end

  def mailbox_provider_from(account, claimed)
    raw = (account["type"] || account[:type] || account["provider"] || claimed).to_s.upcase
    if raw.include?("OUTLOOK") || raw.include?("MICROSOFT")
      "outlook"
    else
      "gmail"
    end
  end

  def mailbox_email(account)
    account["name"].presence ||
      account.dig("connection_params", "mail") ||
      account.dig("object", "name") ||
      account["id"]
  end

  def register_mailbox_webhook(organization)
    result = Email::EnsureMailboxWebhook.execute(organization: organization, client: client)
    return if result.success?

    Rails.logger.warn("Unipile webhook registration skipped: #{result.errors}")
  rescue Faraday::Error => e
    Rails.logger.warn("Unipile webhook registration skipped: #{e.message}")
  end
end
