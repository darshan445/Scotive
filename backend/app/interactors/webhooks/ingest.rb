# frozen_string_literal: true

require "base64"
require "digest"
require "json"
require "openssl"

# Webhooks::Ingest Interactor
# Purpose: Verify provider signature, persist webhook_events, enqueue process. No provider I/O.
# Methods:
# - execute

class Webhooks::Ingest
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(provider:, raw_body:, signature:)
    new(provider: provider, raw_body: raw_body, signature: signature).execute
  end

  def initialize(provider:, raw_body:, signature:)
    @provider = provider.to_s
    @raw_body = raw_body.to_s
    @signature = signature.to_s
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Webhook payload is required") if raw_body.blank?

      verify_signature!
      payload = parse_payload!
      created_ids = []
      persist_events!(payload).each do |record, created|
        next unless created

        created_ids << record.id
        Webhooks::ProcessEventJob.perform_later(record.id)
      end

      { accepted: true, count: created_ids.size }
    end
  end

  private

  attr_reader :provider, :raw_body, :signature

  def verify_signature!
      case provider
      when "qbo" then verify_qbo!
      when "xero" then verify_xero!
      when "gmail" then verify_unipile!
      else
        raise_string_error("Unsupported webhook provider")
      end
    end

    def verify_xero!
      key = ENV["XERO_WEBHOOK_KEY"].to_s
      raise_string_error("Xero webhook key is not configured") if key.blank?
      raise_string_error("Invalid Xero webhook signature") if signature.blank?

      digest = OpenSSL::HMAC.digest("SHA256", key, raw_body)
      expected = Base64.strict_encode64(digest)
      raise_string_error("Invalid Xero webhook signature") unless secure_match?(expected, signature)
    end

    def verify_qbo!
    token = ENV["QBO_WEBHOOK_VERIFIER_TOKEN"].to_s
    raise_string_error("QuickBooks webhook verifier token is not configured") if token.blank?
    raise_string_error("Invalid QuickBooks webhook signature") if signature.blank?

    digest = OpenSSL::HMAC.digest("SHA256", token, raw_body)
    expected = Base64.strict_encode64(digest)
    raise_string_error("Invalid QuickBooks webhook signature") unless secure_match?(expected, signature)
  end

  def verify_unipile!
    secret = ENV["UNIPILE_WEBHOOK_SECRET"].to_s
    raise_string_error("Unipile webhook secret is not configured") if secret.blank?
    raise_string_error("Invalid Unipile webhook signature") unless secure_match?(secret, signature)
  end

  def secure_match?(expected, actual)
    a = expected.to_s
    b = actual.to_s
    return false if a.blank? || b.blank? || a.bytesize != b.bytesize

    ActiveSupport::SecurityUtils.secure_compare(a, b)
  end

  def parse_payload!
    JSON.parse(raw_body)
  rescue JSON::ParserError
    raise_string_error("Webhook payload is not valid JSON")
  end

  def persist_events!(payload)
    expanded_rows(payload).compact.map { |row| find_or_insert!(row) }
  end

  def expanded_rows(payload)
    case provider
    when "qbo" then qbo_rows(payload)
    when "xero" then xero_rows(payload)
    else [ unipile_row(payload) ]
    end
  end

  def xero_rows(payload)
    events = Array(payload["events"])
    events.filter_map do |event|
      next unless event["eventCategory"].to_s.upcase == "INVOICE"

      tenant_id = event["tenantId"].to_s
      {
        provider: "xero",
        external_event_id: [
          "xero", tenant_id, event["resourceId"], event["eventType"], event["eventDateUtc"]
        ].join(":"),
        organization: organization_for_xero(tenant_id),
        integration: integration_for_xero(tenant_id),
        payload: {
          "tenantId" => tenant_id,
          "resourceId" => event["resourceId"],
          "eventCategory" => event["eventCategory"],
          "eventType" => event["eventType"],
          "eventDateUtc" => event["eventDateUtc"]
        }
      }
    end
  end

  def qbo_rows(payload)
    notifications = Array(payload["eventNotifications"])
    raise_string_error("QuickBooks webhook is missing eventNotifications") if notifications.empty?

    notifications.flat_map do |notification|
      realm_id = notification["realmId"].to_s
      entities = Array(notification.dig("dataChangeEvent", "entities"))
      entities.map do |entity|
        {
          provider: "qbo",
          external_event_id: [
            "qbo", realm_id, entity["name"], entity["id"], entity["operation"], entity["lastUpdated"]
          ].join(":"),
          organization: organization_for_qbo(realm_id),
          integration: integration_for_qbo(realm_id),
          payload: {
            "realmId" => realm_id,
            "name" => entity["name"],
            "id" => entity["id"],
            "operation" => entity["operation"],
            "lastUpdated" => entity["lastUpdated"]
          }
        }
      end
    end
  end

  def unipile_row(payload)
    account_id = payload["account_id"].to_s
    integration = Integration.mailbox.connected.find_by(external_account_id: account_id)
    return if integration.blank?

    event = payload["event"].presence || "mail_received"
    email_id = payload["email_id"].presence || Digest::SHA256.hexdigest(raw_body)[0, 32]
    {
      provider: integration.provider,
      external_event_id: [ "unipile", account_id, event, email_id ].join(":"),
      organization: integration.organization,
      integration: integration,
      payload: payload
    }
  end

  def find_or_insert!(row)
    existing = WebhookEvent.find_by(provider: row[:provider], external_event_id: row[:external_event_id])
    return [ existing, false ] if existing.present?

    inserted = WebhookEvent.insert_all(
      [ {
        organization_id: row[:organization]&.id,
        integration_id: row[:integration]&.id,
        provider: row[:provider],
        external_event_id: row[:external_event_id],
        payload: row[:payload],
        status: "pending",
        created_at: Time.current
      } ],
      unique_by: %i[provider external_event_id],
      record_timestamps: false,
      returning: %w[id]
    )
    record = WebhookEvent.find_by!(provider: row[:provider], external_event_id: row[:external_event_id])
    [ record, inserted.rows.any? ]
  end

  def organization_for_qbo(realm_id)
    integration_for_qbo(realm_id)&.organization
  end

  def integration_for_qbo(realm_id)
    return if realm_id.blank?

    @qbo_integrations ||= {}
    @qbo_integrations[realm_id] ||= Integration.accounting.connected.find_by(provider: "qbo", external_account_id: realm_id)
  end

  def organization_for_xero(tenant_id)
    integration_for_xero(tenant_id)&.organization
  end

  def integration_for_xero(tenant_id)
    return if tenant_id.blank?

    @xero_integrations ||= {}
    @xero_integrations[tenant_id] ||= Integration.accounting.connected.find_by(provider: "xero", external_account_id: tenant_id)
  end
end
