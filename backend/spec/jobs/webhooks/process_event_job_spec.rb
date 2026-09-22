# frozen_string_literal: true

require "rails_helper"

RSpec.describe Webhooks::ProcessEventJob, type: :job do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let(:event) do
    WebhookEvent.create!(
      organization: organization,
      provider: "qbo",
      external_event_id: "qbo:1",
      payload: { "name" => "Invoice", "id" => "95" },
      status: "pending",
      created_at: Time.current
    )
  end

  it "does not re-raise decryption failures" do
    allow(Webhooks::ProcessEvent).to receive(:execute).and_return(
      OpenStruct.new(success?: false, errors: [ "QuickBooks credentials could not be decrypted — reconnect QuickBooks" ])
    )

    expect { described_class.perform_now(event.id) }.not_to raise_error
    expect(event.reload.status).to eq("failed")
  end

  it "re-raises other processing failures for retry" do
    allow(Webhooks::ProcessEvent).to receive(:execute).and_return(
      OpenStruct.new(success?: false, errors: [ "QuickBooks timed out" ])
    )

    expect { described_class.perform_now(event.id) }.to raise_error(StandardError, /timed out/)
    expect(event.reload.status).to eq("failed")
  end
end
