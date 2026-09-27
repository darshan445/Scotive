# frozen_string_literal: true

# Xero::CompleteOauth Interactor
# Purpose: Exchange the Xero code, load the tenant, persist the accounting integration.
# Methods:
# - execute

class Xero::CompleteOauth
  include ExecuteMethodHelper
  include LogHelper
  include OauthStateHelper

  def self.execute(code:, state:, error: nil, error_description: nil, client: Xero::XeroClient.new)
    new(code: code, state: state, error: error, error_description: error_description, client: client).execute
  end

  def initialize(code:, state:, error:, error_description:, client:)
    @code = code.to_s
    @state = state.to_s
    @error = error.to_s
    @error_description = error_description.to_s
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error(oauth_error_message) if error.present?
      raise_string_error("Missing authorization code") if code.blank?

      claims = decode_oauth_state!(state)
      organization = Organization.find_by(id: claims["organization_id"])
      raise_string_error("Organization not found") if organization.blank?

      tokens = exchange_tokens
      access_token = tokens["access_token"] || tokens[:access_token]
      refresh_token = tokens["refresh_token"] || tokens[:refresh_token]
      expires_in = (tokens["expires_in"] || tokens[:expires_in]).to_i
      raise_string_error("Xero did not return an access token") if access_token.blank?

      tenant = pick_tenant(access_token)
      tenant_id = tenant["tenantId"].to_s
      raise_string_error("Xero did not return an organisation") if tenant_id.blank?

      company_name = organisation_name(access_token, tenant_id).presence ||
        tenant["tenantName"].presence ||
        "Xero organisation"

      integration = organization.integrations.accounting.find_or_initialize_by(provider: "xero")
      integration.assign_attributes(
        category: "accounting",
        external_account_id: tenant_id,
        account_name: company_name,
        access_token: access_token,
        refresh_token: refresh_token,
        token_expires_at: expires_in.positive? ? Time.current + expires_in.seconds : nil,
        webhook_subscription_id: tenant["id"].to_s.presence,
        connection_status: "connected"
      )
      raise_string_error(integration.errors.full_messages.to_sentence) unless integration.save

      { integration_id: integration.id, tenant_id: tenant_id, company_name: company_name }
    end
  end

  private

  attr_reader :code, :state, :error, :error_description, :client

  def oauth_error_message
    detail = error_description.presence || error
    return detail if detail.match?(/scope/i)
    return "access_denied" if error.match?(/\baccess_denied\b|cancelled/i)

    detail
  end

  def exchange_tokens
    client.exchange_code(code: code, redirect_uri: ENV.fetch("XERO_REDIRECT_URI"))
  rescue Faraday::Error
    raise_string_error("Xero authorization failed")
  end

  def pick_tenant(access_token)
    rows = client.list_connections(access_token: access_token)
    organisation = rows.find { |row| row["tenantType"].to_s == "ORGANISATION" } || rows.first
    raise_string_error("No Xero organisation was authorised") if organisation.blank?

    organisation
  rescue Faraday::Error => e
    raise_string_error("Could not load Xero organisations: #{e.message}")
  end

  def organisation_name(access_token, tenant_id)
    client.get_organisation(tenant_id: tenant_id, access_token: access_token)["Name"]
  rescue Faraday::Error
    nil
  end
end
