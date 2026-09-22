# frozen_string_literal: true

# Quickbooks::CompleteOauth Interactor
# Purpose: Exchange the Intuit code, load company info, persist the accounting integration.
# Methods:
# - execute

class Quickbooks::CompleteOauth
  include ExecuteMethodHelper
  include LogHelper
  include OauthStateHelper

  def self.execute(code:, realm_id:, state:, error: nil, client: Quickbooks::QuickbookClient.new)
    new(code: code, realm_id: realm_id, state: state, error: error, client: client).execute
  end

  def initialize(code:, realm_id:, state:, error:, client:)
    @code = code.to_s
    @realm_id = realm_id.to_s
    @state = state.to_s
    @error = error.to_s
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("access_denied") if error.present? && error.match?(/denied|cancelled/i)
      raise_string_error(error.presence || "QuickBooks authorization failed") if error.present?
      raise_string_error("Missing authorization code") if code.blank?
      raise_string_error("Missing QuickBooks company (realm) id") if realm_id.blank?

      claims = decode_oauth_state!(state)
      organization = Organization.find_by(id: claims["organization_id"])
      raise_string_error("Organization not found") if organization.blank?

      tokens = exchange_tokens
      access_token = tokens["access_token"] || tokens[:access_token]
      refresh_token = tokens["refresh_token"] || tokens[:refresh_token]
      expires_in = (tokens["expires_in"] || tokens[:expires_in]).to_i
      raise_string_error("QuickBooks did not return an access token") if access_token.blank?

      company = fetch_company(access_token)
      company_name = company.dig("CompanyInfo", "CompanyName").presence || "QuickBooks company"

      integration = organization.integrations.accounting.find_or_initialize_by(provider: "qbo")
      integration.assign_attributes(
        category: "accounting",
        external_account_id: realm_id,
        account_name: company_name,
        access_token: access_token,
        refresh_token: refresh_token,
        token_expires_at: expires_in.positive? ? Time.current + expires_in.seconds : nil,
        connection_status: "connected"
      )
      raise_string_error(integration.errors.full_messages.to_sentence) unless integration.save

      { integration_id: integration.id, realm_id: realm_id, company_name: company_name }
    end
  end

  private

  attr_reader :code, :realm_id, :state, :error, :client

  def exchange_tokens
    client.exchange_code(code: code, redirect_uri: ENV.fetch("QBO_REDIRECT_URI"))
  rescue Faraday::Error
    raise_string_error("QuickBooks authorization failed")
  end

  def fetch_company(access_token)
    client.get_company_info(realm_id: realm_id, access_token: access_token)
  rescue Faraday::Error => e
    raise_string_error(company_load_error(e))
  end

  def company_load_error(error)
    detail = error.message.to_s
    host = ENV.fetch("QBO_ENV", "sandbox")
    if detail.match?(/401|403|AuthenticationFailed|AuthorizationFailed/i)
      "Could not load QuickBooks company (#{host} API rejected the token). " \
        "Reconnect and confirm QBO_ENV matches the company (sandbox vs production). #{detail}"
    else
      "Could not load QuickBooks company: #{detail}"
    end
  end
end
