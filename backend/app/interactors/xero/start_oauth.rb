# frozen_string_literal: true

# Xero::StartOauth Interactor
# Purpose: Build the Xero authorization URL for the current organization.
# Methods:
# - execute

class Xero::StartOauth
  include ExecuteMethodHelper
  include LogHelper
  include OauthStateHelper

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
      raise_string_error("XERO_CLIENT_ID is missing") if ENV["XERO_CLIENT_ID"].blank?
      raise_string_error("XERO_REDIRECT_URI is missing") if redirect_uri.blank?

      state = encode_oauth_state(
        "organization_id" => organization.id,
        "provider" => "xero"
      )
      { authorization_url: client.authorization_url(state: state, redirect_uri: redirect_uri) }
    end
  end

  private

  attr_reader :organization, :client

  def redirect_uri
    ENV["XERO_REDIRECT_URI"].to_s
  end
end
