# frozen_string_literal: true

require "rails_helper"

RSpec.describe Settings::Update do
  let(:organization) { Organization.create!(name: "Ada's workspace") }

  it "persists timezone, Friendly auto-send, and reminder slots" do
    result = described_class.execute(
      organization: organization,
      attrs: {
        daily_digest_timezone: "America/New_York",
        friendly_auto_send: false,
        friendly_reminders: {
          before_due: { enabled: true, days: 2 },
          on_due: { enabled: true },
          overdue: { enabled: true, days: 6 }
        },
        daily_digest_enabled: true,
        daily_digest_hour: 7
      }
    )

    expect(result.success?).to eq(true)
    organization.reload
    expect(organization.time_zone).to eq("America/New_York")
    expect(organization.friendly_auto_send).to eq(false)
    expect(organization.friendly_reminders).to eq(
      "before_due" => { "enabled" => true, "days" => 2 },
      "on_due" => { "enabled" => true },
      "overdue" => { "enabled" => true, "days" => 6 }
    )
    expect(organization.ladder_offsets).to eq([ -2, 0, 6 ])
    expect(result.data[:daily_digest_timezone]).to eq("America/New_York")
    expect(result.data[:friendly_reminders]["before_due"]["days"]).to eq(2)
    expect(result.data[:last_digest_sent_at]).to be_nil
  end

  it "accepts a legacy signed offset array" do
    result = described_class.execute(organization: organization, attrs: { escalation_offsets: [ -2, 0, 6 ] })
    expect(result.success?).to eq(true)
    expect(organization.reload.ladder_offsets).to eq([ -2, 0, 6 ])
  end

  it "lets a workspace turn off one Friendly reminder" do
    result = described_class.execute(
      organization: organization,
      attrs: {
        friendly_reminders: {
          before_due: { enabled: true, days: 3 },
          on_due: { enabled: false },
          overdue: { enabled: true, days: 7 }
        }
      }
    )

    expect(result.success?).to eq(true)
    expect(organization.reload.ladder_offsets).to eq([ -3, 7 ])
    expect(Cadence::Steps.last_friendly_offset(organization)).to eq(7)
    expect(result.data[:friendly_reminders]["on_due"]["enabled"]).to eq(false)
  end

  it "rejects an unknown timezone" do
    result = described_class.execute(organization: organization, attrs: { time_zone: "Not/AZone" })
    expect(result.success?).to eq(false)
    expect(result.errors.to_s).to match(/Unknown timezone/)
  end
end
