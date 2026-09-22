# frozen_string_literal: true

require "rails_helper"

RSpec.describe Webhooks::ReplayPending do
  include ActiveJob::TestHelper

  after { clear_enqueued_jobs }

  it "re-enqueues pending events for the organization" do
    organization = Organization.create!(name: "Ada's workspace")
    pending = WebhookEvent.create!(
      organization: organization,
      provider: "qbo",
      external_event_id: "qbo:pending-1",
      payload: { "name" => "Invoice", "id" => "581", "operation" => "Emailed" },
      status: "pending",
      created_at: Time.current
    )
    WebhookEvent.create!(
      organization: organization,
      provider: "qbo",
      external_event_id: "qbo:done-1",
      payload: { "name" => "Invoice", "id" => "1" },
      status: "processed",
      created_at: Time.current
    )

    expect {
      result = described_class.execute(organization: organization)
      expect(result.success?).to eq(true)
      expect(result.data[:enqueued]).to eq(1)
    }.to have_enqueued_job(Webhooks::ProcessEventJob).with(pending.id)
  end
end
