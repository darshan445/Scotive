# frozen_string_literal: true

# Email::StartOauth Interactor
# Purpose: Create a Unipile hosted-auth URL for Gmail or Outlook.
# Methods:
# - execute

class Email::StartOauth
  include ExecuteMethodHelper
  include LogHelper
  include OauthStateHelper

  def self.execute(organization:, provider:, client: Email::EmailClient.new)
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
      raise_string_error("UNIPILE_DSN is missing") if ENV["UNIPILE_DSN"].blank?
      raise_string_error("UNIPILE_API_KEY is missing") if ENV["UNIPILE_API_KEY"].blank?

      mailbox_provider = map_mailbox_provider
      unipile_provider = mailbox_provider == "outlook" ? "OUTLOOK" : "GOOGLE"
      state = encode_oauth_state(
        "organization_id" => organization.id,
        "provider" => mailbox_provider
      )

      body = request_hosted_link(mailbox_provider, state, unipile_provider)
      url = body.is_a?(Hash) ? (body["url"] || body[:url]).to_s : ""
      raise_string_error("Unipile did not return a hosted auth URL") if url.blank?

      { authorization_url: url }
    end
  end

  private

  attr_reader :organization, :provider, :client

  def map_mailbox_provider
    case provider
    when "outlook", "microsoft" then "outlook"
    when "gmail", "google", "" then "gmail"
    else
      raise_string_error("Unsupported mailbox provider")
    end
  end

  def public_api
    ENV.fetch("PUBLIC_API_URL", "http://localhost:3000").to_s.chomp("/")
  end

  def frontend
    ENV.fetch("FRONTEND_URL", "http://localhost:3001").to_s.chomp("/")
  end

  def request_hosted_link(mailbox_provider, state, unipile_provider)
    client.create_hosted_auth_link(
      "type" => "create",
      "providers" => [ unipile_provider ],
      "api_url" => ENV.fetch("UNIPILE_DSN").to_s.chomp("/"),
      "expiresOn" => 20.minutes.from_now.utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
      "name" => organization.id.to_s,
      "success_redirect_url" => success_url(state),
      "failure_redirect_url" => failure_url(mailbox_provider),
      "bypass_success_screen" => true
    )
  rescue Faraday::Error
    raise_string_error("Could not start mailbox connection")
  end

  def success_url(state)
    "#{public_api}/api/v1/gmail/oauth/callback?#{ { state: state }.to_query }"
  end

  def failure_url(mailbox_provider)
    "#{frontend}/dashboard?mail=error&provider=#{mailbox_provider == "outlook" ? "outlook" : "google"}"
  end
end
