# frozen_string_literal: true

require "rails_helper"
require "base64"
require "openssl"

RSpec.describe Webhooks::Ingest do
  include ActiveJob::TestHelper

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:verifier) { "qbo-verifier-token" }
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "at",
      connection_status: "connected"
    )
  end

  def sign(body)
    Base64.strict_encode64(OpenSSL::HMAC.digest("SHA256", verifier, body))
  end

  def qbo_body(operation: "Update")
    {
      "eventNotifications" => [
        {
          "realmId" => "realm-1",
          "dataChangeEvent" => {
            "entities" => [
              {
                "name" => "Invoice",
                "id" => "95",
                "operation" => operation,
                "lastUpdated" => "2026-09-18T10:00:00.000Z"
              }
            ]
          }
        }
      ]
    }.to_json
  end

  around do |example|
    prior = ENV["QBO_WEBHOOK_VERIFIER_TOKEN"]
    ENV["QBO_WEBHOOK_VERIFIER_TOKEN"] = verifier
    example.run
    ENV["QBO_WEBHOOK_VERIFIER_TOKEN"] = prior
  end

  after { clear_enqueued_jobs }

  it "persists a pending event and enqueues process" do
    body = qbo_body
    result = nil
    expect {
      result = described_class.execute(provider: "qbo", raw_body: body, signature: sign(body))
    }.to have_enqueued_job(Webhooks::ProcessEventJob)

    expect(result.success?).to eq(true)
    event = WebhookEvent.last
    expect(event.status).to eq("pending")
    expect(event.provider).to eq("qbo")
    expect(event.organization_id).to eq(organization.id)
    expect(event.payload["id"]).to eq("95")
  end

  it "is idempotent for the same QBO entity event" do
    body = qbo_body
    described_class.execute(provider: "qbo", raw_body: body, signature: sign(body))
    expect {
      described_class.execute(provider: "qbo", raw_body: body, signature: sign(body))
    }.not_to have_enqueued_job(Webhooks::ProcessEventJob)
    expect(WebhookEvent.count).to eq(1)
  end

  it "does not persist Unipile mail from an account that is not connected" do
    prior = ENV["UNIPILE_WEBHOOK_SECRET"]
    ENV["UNIPILE_WEBHOOK_SECRET"] = "unipile-secret"
    body = {
      "event" => "mail_received",
      "account_id" => "someone-else",
      "email_id" => "m-1",
      "subject" => "Initial deposit initiated"
    }.to_json

    result = described_class.execute(provider: "gmail", raw_body: body, signature: "unipile-secret")
    ENV["UNIPILE_WEBHOOK_SECRET"] = prior

    expect(result.success?).to eq(true)
    expect(result.data[:count]).to eq(0)
    expect(WebhookEvent.count).to eq(0)
  end

  it "persists Unipile mail once when two subscriptions deliver the same event" do
    prior = ENV["UNIPILE_WEBHOOK_SECRET"]
    ENV["UNIPILE_WEBHOOK_SECRET"] = "unipile-secret"
    mailbox = organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
    body = {
      "event" => "mail_received",
      "account_id" => "acc-gmail",
      "email_id" => "Hpv9CafGVYyMrylLaPPYKA",
      "subject" => "Initial deposit initiated"
    }.to_json

    first = described_class.execute(provider: "gmail", raw_body: body, signature: "unipile-secret")
    second = described_class.execute(provider: "gmail", raw_body: body, signature: "unipile-secret")
    ENV["UNIPILE_WEBHOOK_SECRET"] = prior

    expect(first.success?).to eq(true)
    expect(first.data[:count]).to eq(1)
    expect(second.data[:count]).to eq(0)
    expect(WebhookEvent.where(integration: mailbox).count).to eq(1)
  end

  it "rejects a bad HMAC" do
    result = described_class.execute(provider: "qbo", raw_body: qbo_body, signature: "nope")
    expect(result.success?).to eq(false)
    expect(result.errors).to match(/signature/)
    expect(WebhookEvent.count).to eq(0)
  end

  describe "Xero" do
    let(:xero_key) { "xero-webhook-key" }

    def xero_sign(body)
      Base64.strict_encode64(OpenSSL::HMAC.digest("SHA256", xero_key, body))
    end

    around do |example|
      prior = ENV["XERO_WEBHOOK_KEY"]
      ENV["XERO_WEBHOOK_KEY"] = xero_key
      example.run
      ENV["XERO_WEBHOOK_KEY"] = prior
    end

    it "persists an invoice event and enqueues process" do
      organization.integrations.create!(
        category: "accounting",
        provider: "xero",
        external_account_id: "tenant-1",
        account_name: "Studio",
        access_token: "at",
        connection_status: "connected"
      )
      body = {
        "events" => [
          {
            "resourceId" => "inv-95",
            "eventDateUtc" => "2026-09-18T10:00:00.000Z",
            "eventType" => "UPDATE",
            "eventCategory" => "INVOICE",
            "tenantId" => "tenant-1"
          }
        ]
      }.to_json

      result = nil
      expect {
        result = described_class.execute(provider: "xero", raw_body: body, signature: xero_sign(body))
      }.to have_enqueued_job(Webhooks::ProcessEventJob)

      expect(result.success?).to eq(true)
      event = WebhookEvent.last
      expect(event.provider).to eq("xero")
      expect(event.payload["resourceId"]).to eq("inv-95")
    end

    it "accepts intent-to-receive with no events" do
      body = { "events" => [], "firstEventSequence" => 0, "lastEventSequence" => 0 }.to_json
      result = described_class.execute(provider: "xero", raw_body: body, signature: xero_sign(body))

      expect(result.success?).to eq(true)
      expect(result.data[:count]).to eq(0)
      expect(WebhookEvent.count).to eq(0)
    end

    it "rejects a bad Xero HMAC" do
      body = { "events" => [] }.to_json
      result = described_class.execute(provider: "xero", raw_body: body, signature: "nope")
      expect(result.success?).to eq(false)
      expect(result.errors).to match(/signature/)
    end
  end
end
