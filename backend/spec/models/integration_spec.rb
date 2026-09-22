# frozen_string_literal: true

require "rails_helper"

RSpec.describe Integration, type: :model do
  let(:organization) { Organization.create!(name: "Acme") }

  it "stores a QBO accounting connection" do
    integration = described_class.create!(
      organization: organization,
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Acme Operations",
      access_token: "secret-access",
      refresh_token: "secret-refresh",
      connection_status: "connected"
    )

    expect(integration).to be_accounting
    expect(integration).to be_connected
    expect(integration.reload.access_token).to eq("secret-access")
  end

  it "stores Gmail and Outlook as mailbox providers, not Unipile" do
    gmail = described_class.create!(
      organization: organization,
      category: "mailbox",
      provider: "gmail",
      external_account_id: "owner@acme.com"
    )
    outlook = described_class.create!(
      organization: organization,
      category: "mailbox",
      provider: "outlook",
      external_account_id: "ap@acme.com"
    )

    expect(gmail).to be_mailbox
    expect(outlook.provider).to eq("outlook")
    expect(described_class::PROVIDERS).not_to include("unipile")
  end

  it "rejects Unipile as a provider" do
    integration = described_class.new(
      organization: organization,
      category: "mailbox",
      provider: "unipile"
    )

    expect(integration).not_to be_valid
    expect(integration.errors[:provider]).to be_present
  end

  it "rejects a mailbox provider on an accounting category" do
    integration = described_class.new(
      organization: organization,
      category: "accounting",
      provider: "gmail"
    )

    expect(integration).not_to be_valid
    expect(integration.errors[:provider]).to be_present
  end

  it "destroys webhook_events when the integration is removed" do
    integration = described_class.create!(
      organization: organization,
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail"
    )
    WebhookEvent.create!(
      organization: organization,
      integration: integration,
      provider: "gmail",
      external_event_id: "evt-1",
      payload: { "event" => "mail_received" },
      created_at: Time.current
    )

    integration.destroy!
    expect(WebhookEvent.where(integration_id: integration.id)).to be_empty
  end
end
