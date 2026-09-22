# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::EnsureMailboxWebhook do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:client) { instance_double(Email::EmailClient) }

  around do |example|
    prior_url = ENV["PUBLIC_API_URL"]
    prior_dsn = ENV["UNIPILE_DSN"]
    prior_key = ENV["UNIPILE_API_KEY"]
    prior_secret = ENV["UNIPILE_WEBHOOK_SECRET"]
    example.run
    ENV["PUBLIC_API_URL"] = prior_url
    ENV["UNIPILE_DSN"] = prior_dsn
    ENV["UNIPILE_API_KEY"] = prior_key
    ENV["UNIPILE_WEBHOOK_SECRET"] = prior_secret
  end

  it "skips registration for a local public URL" do
    ENV["PUBLIC_API_URL"] = "http://localhost:3000"
    result = described_class.execute(organization: organization, client: client)
    expect(result.success?).to eq(true)
    expect(result.data[:registered]).to eq(false)
    expect(result.data[:reason]).to eq("public_api_url_local")
  end

  it "creates a Unipile email webhook when missing" do
    ENV["PUBLIC_API_URL"] = "https://example.ngrok-free.dev"
    ENV["UNIPILE_DSN"] = "https://api.unipile.test"
    ENV["UNIPILE_API_KEY"] = "key"
    ENV["UNIPILE_WEBHOOK_SECRET"] = "secret"
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-1",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
    allow(client).to receive(:list_webhooks).and_return({ "items" => [] })
    allow(client).to receive(:create_webhook).and_return({ "object" => "WebhookCreated", "webhook_id" => "wh-1" })

    result = described_class.execute(organization: organization, client: client)
    expect(result.success?).to eq(true)
    expect(result.data[:registered]).to eq(true)
    expect(client).to have_received(:create_webhook).with(hash_including(
      name: "wherewasthis-email",
      source: "email",
      events: %w[mail_received mail_sent],
      request_url: "https://example.ngrok-free.dev/api/v1/gmail/webhooks"
    ))
    expect(organization.integrations.mailbox.first.webhook_subscription_id).to eq("wh-1")
    expect(organization.integrations.mailbox.first.webhook_expires_at).to be_within(2.seconds).of(7.days.from_now)
  end

  it "keeps wherewasthis-email and deletes leftover names on the same URL" do
    ENV["PUBLIC_API_URL"] = "https://example.ngrok-free.dev"
    ENV["UNIPILE_DSN"] = "https://api.unipile.test"
    ENV["UNIPILE_API_KEY"] = "key"
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-1",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
    allow(client).to receive(:list_webhooks).and_return(
      "items" => [
        { "id" => "wh-cost", "request_url" => "https://example.ngrok-free.dev/api/v1/gmail/webhooks", "source" => "email", "name" => "costmydish-email" },
        { "id" => "wh-keep", "request_url" => "https://example.ngrok-free.dev/api/v1/gmail/webhooks", "source" => "email", "name" => "wherewasthis-email" },
        { "id" => "wh-where", "request_url" => "https://example.ngrok-free.dev/api/v1/gmail/webhooks", "source" => "email", "name" => "wherewasthis" }
      ]
    )
    allow(client).to receive(:delete_webhook)

    result = described_class.execute(organization: organization, client: client)
    expect(result.success?).to eq(true)
    expect(result.data[:webhook_id]).to eq("wh-keep")
    expect(client).to have_received(:delete_webhook).with("wh-cost")
    expect(client).to have_received(:delete_webhook).with("wh-where")
  end
end
