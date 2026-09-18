# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::MorningJob, type: :job do
  it "schedules cadence for organizations with a connected integration" do
    organization = Organization.create!(name: "Ada's workspace")
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
    allow(Cadence::Schedule).to receive(:execute).and_return(OpenStruct.new(success?: true, data: { created: 0 }))

    described_class.perform_now
    expect(Cadence::Schedule).to have_received(:execute).with(organization: organization)
  end
end
