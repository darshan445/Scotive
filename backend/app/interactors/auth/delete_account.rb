# frozen_string_literal: true

# Auth::DeleteAccount Interactor
# Purpose: Confirm email, revoke integrations best-effort, then destroy the org and owner.
# Methods:
# - execute

class Auth::DeleteAccount
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(user:, confirm_email:, token: nil, qbo_client: Quickbooks::QuickbookClient.new, xero_client: Xero::XeroClient.new, email_client: Email::EmailClient.new)
    new(
      user: user,
      confirm_email: confirm_email,
      token: token,
      qbo_client: qbo_client,
      xero_client: xero_client,
      email_client: email_client
    ).execute
  end

  def initialize(user:, confirm_email:, token:, qbo_client:, xero_client:, email_client:)
    @user = user
    @confirm_email = confirm_email.to_s.strip.downcase
    @token = token.to_s.delete_prefix("Bearer ").strip
    @qbo_client = qbo_client
    @xero_client = xero_client
    @email_client = email_client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("You must be signed in") if user.blank?
      raise_string_error("Type your email to confirm") if confirm_email.blank?
      raise_string_error("Email confirmation does not match") unless confirm_email == user.email.to_s.downcase
      raise_string_error("Only the workspace owner can delete this account") unless user.role == "owner"

      organization = user.organization
      raise_string_error("Organization is required") if organization.blank?

      revoke_remote_connections(organization)
      organization.destroy!
      denylist_current_token

      { deleted: true }
    end
  end

  private

  attr_reader :user, :confirm_email, :token, :qbo_client, :xero_client, :email_client

  def revoke_remote_connections(organization)
    organization.integrations.mailbox.each do |integration|
      next if integration.external_account_id.blank?

      email_client.delete_account(integration.external_account_id)
    rescue Faraday::Error => e
      Rails.logger.warn("Unipile delete during account removal failed: #{e.message}")
    end

    organization.integrations.accounting.where(provider: "qbo").each do |integration|
      remote_token = integration.refresh_token.presence || integration.access_token
      next if remote_token.blank?

      qbo_client.revoke_token(remote_token)
    rescue Faraday::Error => e
      Rails.logger.warn("QBO revoke during account removal failed: #{e.message}")
    end

    if organization.integrations.accounting.exists?(provider: "xero")
      Xero::Disconnect.execute(organization: organization, client: xero_client)
    end
  rescue Faraday::Error => e
    Rails.logger.warn("Xero revoke during account removal failed: #{e.message}")
  end

  def denylist_current_token
    return if token.blank?

    payload = Warden::JWTAuth::TokenDecoder.new.call(token)
    JwtDenylist.revoke_jwt(payload, user)
  rescue StandardError => e
    Rails.logger.warn("JWT denylist during account removal failed: #{e.message}")
  end
end
