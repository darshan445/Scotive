# frozen_string_literal: true

require "uri"

# Email::EnsureMailboxWebhook Interactor
# Purpose: Register a DSN-wide Unipile mail_received/mail_sent webhook if missing.
# Methods:
# - execute

class Email::EnsureMailboxWebhook
  include ExecuteMethodHelper
  include LogHelper

  WEBHOOK_NAME = "costmydish-email"

  def self.execute(organization:, client: Email::EmailClient.new)
    new(organization: organization, client: client).execute
  end

  def initialize(organization:, client:)
    @organization = organization
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      if skip_reason
        { registered: false, reason: skip_reason }
      else
        webhook_id = existing_webhook_id || create_webhook_id!
        stamp_mailboxes!(webhook_id)
        { registered: true, webhook_id: webhook_id, request_url: request_url }
      end
    end
  end

  private

  attr_reader :organization, :client

  def skip_reason
    return "public_api_url_missing" if public_api_url.blank?
    return "public_api_url_local" if local_url?
    return "unipile_not_configured" if ENV["UNIPILE_DSN"].blank? || ENV["UNIPILE_API_KEY"].blank?

    nil
  end

  def existing_webhook_id
    items.find { |row| matching_webhook?(row) }&.dig("id")
  end

  def items
    body = client.list_webhooks
    raw = body.is_a?(Hash) ? (body["items"] || body["webhooks"] || []) : Array(body)
    Array(raw).map { |row| row.stringify_keys }
  rescue Faraday::Error
    []
  end

  def matching_webhook?(row)
    row["request_url"].to_s.chomp("/") == request_url.chomp("/") &&
      row["source"].to_s == "email" &&
      row["name"].to_s == WEBHOOK_NAME
  end

  def create_webhook_id!
    payload = {
      name: WEBHOOK_NAME,
      request_url: request_url,
      format: "json",
      source: "email",
      events: %w[mail_received mail_sent],
      headers: webhook_headers
    }
    created = client.create_webhook(payload)
    created = created.stringify_keys if created.is_a?(Hash)
    id = created.is_a?(Hash) ? (created["id"] || created["webhook_id"] || created.dig("webhook", "id")) : nil
    raise_string_error("Unipile did not return a webhook id") if id.blank?

    id
  rescue Faraday::Error
    raise_string_error("Unipile webhook registration failed")
  end

  def webhook_headers
    headers = [ { key: "Content-Type", value: "application/json" } ]
    secret = ENV["UNIPILE_WEBHOOK_SECRET"].to_s
    headers << { key: "Unipile-Auth", value: secret } if secret.present?
    headers
  end

  def stamp_mailboxes!(webhook_id)
    organization.integrations.mailbox.connected.update_all(
      webhook_subscription_id: webhook_id,
      webhook_expires_at: 7.days.from_now,
      updated_at: Time.current
    )
  end

  def request_url
    "#{public_api_url}/api/v1/gmail/webhooks"
  end

  def public_api_url
    ENV["PUBLIC_API_URL"].to_s.chomp("/")
  end

  def local_url?
    host = begin
      URI.parse(public_api_url).host.to_s
    rescue URI::InvalidURIError
      public_api_url
    end
    host.blank? || host.match?(/\A(localhost|127\.0\.0\.1)\z/i)
  end
end
