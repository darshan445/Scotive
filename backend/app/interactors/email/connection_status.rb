# frozen_string_literal: true

# Email::ConnectionStatus Interactor
# Purpose: Serialize mailbox integrations (Gmail and/or Outlook) for the connect UI.
# Methods:
# - execute

class Email::ConnectionStatus
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

      rows = organization.integrations.mailbox.order(:provider)
      connections = rows.map { |integration| connection_hash(integration) }
      active = rows.find(&:connected?)
      reauth = rows.find { |row| row.connection_status == "reauth_required" }
      {
        connected: active.present?,
        status: active&.connection_status || reauth&.connection_status || "disconnected",
        can_send: active.present?,
        email: (active || reauth)&.account_name,
        provider: frontend_provider((active || reauth)&.provider),
        connections: connections
      }
    end
  end

  private

  attr_reader :organization

  def connection_hash(integration)
    {
      provider: frontend_provider(integration.provider),
      connected: integration.connected?,
      status: integration.connection_status,
      email: integration.account_name
    }
  end

  def frontend_provider(provider)
    provider == "outlook" ? "outlook" : (provider == "gmail" ? "google" : provider)
  end
end
