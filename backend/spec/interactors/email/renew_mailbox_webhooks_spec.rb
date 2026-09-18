# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::RenewMailboxWebhooks do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:client) { instance_double(Email::EmailClient) }

  around do |example|
    prior_url = ENV["PUBLIC_API_URL"]
    prior_dsn = ENV["UNIPILE_DSN"]
    prior_key = ENV["UNIPILE_API_KEY"]
    example.run
    ENV["PUBLIC_API_URL"] = prior_url
    ENV["UNIPILE_DSN"] = prior_dsn
    ENV["UNIPILE_API_KEY"] = prior_key
  end

  it "renews a mailbox watch due within two days and stamps a 7-day expiry" do
    ENV["PUBLIC_API_URL"] = "https://example.ngrok-free.dev"
    ENV["UNIPILE_DSN"] = "https://api.unipile.test"
    ENV["UNIPILE_API_KEY"] = "key"
    mailbox = organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-1",
      account_name: "owner@studio.com",
      connection_status: "connected",
      webhook_subscription_id: "wh-old",
      webhook_expires_at: 1.day.from_now
    )
    allow(client).to receive(:list_webhooks).and_return(
      "items" => [ { "id" => "wh-old", "request_url" => "https://example.ngrok-free.dev/api/v1/gmail/webhooks", "source" => "email" } ]
    )
    allow(client).to receive(:create_webhook)

    result = described_class.execute(client: client)
    expect(result.success?).to eq(true)
    expect(result.data[:renewed]).to eq(1)
    expect(mailbox.reload.webhook_expires_at).to be_within(2.seconds).of(7.days.from_now)
    expect(client).not_to have_received(:create_webhook)
  end

  it "skips mailboxes whose watch is still valid" do
    ENV["PUBLIC_API_URL"] = "https://example.ngrok-free.dev"
    ENV["UNIPILE_DSN"] = "https://api.unipile.test"
    ENV["UNIPILE_API_KEY"] = "key"
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-1",
      account_name: "owner@studio.com",
      connection_status: "connected",
      webhook_expires_at: 5.days.from_now
    )

    result = described_class.execute(client: client)
    expect(result.data[:renewed]).to eq(0)
  end
end
