# frozen_string_literal: true

require "rails_helper"

RSpec.describe Settings::Update do
  let(:organization) { Organization.create!(name: "Ada's workspace") }

  it "persists timezone and Friendly auto-send" do
    result = described_class.execute(
      organization: organization,
      attrs: {
        daily_digest_timezone: "America/New_York",
        friendly_auto_send: false,
        follow_up_interval_days: 5,
        escalation_offsets: [ -2, 0, 6, 10 ],
        daily_digest_enabled: true,
        daily_digest_hour: 7
      }
    )

    expect(result.success?).to eq(true)
    organization.reload
    expect(organization.time_zone).to eq("America/New_York")
    expect(organization.friendly_auto_send).to eq(false)
    expect(organization.follow_up_interval_days).to eq(5)
    expect(organization.escalation_offsets).to eq([ -2, 0, 6, 10 ])
    expect(result.data[:daily_digest_timezone]).to eq("America/New_York")
    expect(result.data[:last_digest_sent_at]).to be_nil
  end

  it "rejects a short escalation ladder" do
    result = described_class.execute(organization: organization, attrs: { escalation_offsets: [ -3, 0 ] })
    expect(result.success?).to eq(false)
    expect(result.errors.to_s).to match(/four numbers/)
  end

  it "rejects an unknown timezone" do
    result = described_class.execute(organization: organization, attrs: { time_zone: "Not/AZone" })
    expect(result.success?).to eq(false)
    expect(result.errors.to_s).to match(/Unknown timezone/)
  end
end
