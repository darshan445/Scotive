# frozen_string_literal: true

require "rails_helper"

RSpec.describe Quickbooks::RefreshTokens do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:client) { instance_double(Quickbooks::QuickbookClient) }

  def create_qbo!(expires_at:)
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "old-at",
      refresh_token: "rt",
      token_expires_at: expires_at,
      connection_status: "connected"
    )
  end

  it "refreshes tokens that expire before the next 6-hour poll" do
    record = create_qbo!(expires_at: 1.hour.from_now)
    allow(client).to receive(:refresh_access_token).and_return(
      "access_token" => "new-at",
      "refresh_token" => "new-rt",
      "expires_in" => 3600
    )

    result = described_class.execute(client: client)
    expect(result.success?).to eq(true)
    expect(result.data[:refreshed]).to eq(1)
    expect(record.reload.access_token).to eq("new-at")
    expect(record.connection_status).to eq("connected")
    expect(client).to have_received(:refresh_access_token).with(refresh_token: "rt")
  end

  it "marks reauth_required on invalid_grant and skips fresh tokens" do
    dying = create_qbo!(expires_at: 30.minutes.from_now)
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-2",
      account_name: "Other",
      access_token: "fresh-at",
      refresh_token: "rt-2",
      token_expires_at: 12.hours.from_now,
      connection_status: "connected"
    )
    allow(client).to receive(:refresh_access_token).and_raise(Faraday::Error, "invalid_grant")

    result = described_class.execute(client: client)
    expect(result.success?).to eq(true)
    expect(result.data[:reauth]).to eq(1)
    expect(result.data[:skipped]).to eq(1)
    expect(dying.reload.connection_status).to eq("reauth_required")
  end
end
