# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::Morning do
  include ActiveSupport::Testing::TimeHelpers

  let(:organization) { Organization.create!(name: "Ada's workspace") }

  before do
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
    allow(Cadence::Schedule).to receive(:execute).and_return(OpenStruct.new(success?: true, data: { created: 0 }))
  end

  it "runs the morning schedule at 08:00 in the organization timezone" do
    travel_to Time.utc(2026, 9, 18, 8, 0) do
      result = described_class.execute
      expect(result.success?).to eq(true)
      expect(result.data[:ran]).to eq(1)
      expect(Cadence::Schedule).to have_received(:execute).with(organization: organization)
    end
  end

  it "skips when it is not 08:00 locally" do
    travel_to Time.utc(2026, 9, 18, 12, 0) do
      described_class.execute
      expect(Cadence::Schedule).not_to have_received(:execute)
    end
  end

  it "runs at 08:00 Eastern when UTC is 12:00 in September" do
    organization.update!(time_zone: "America/New_York")
    travel_to Time.utc(2026, 9, 18, 12, 0) do
      described_class.execute
      expect(Cadence::Schedule).to have_received(:execute).with(organization: organization)
    end
  end
end
