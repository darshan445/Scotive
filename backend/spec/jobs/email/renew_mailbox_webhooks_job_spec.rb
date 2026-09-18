# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::RenewMailboxWebhooksJob, type: :job do
  it "runs mailbox webhook renewal" do
    allow(Email::RenewMailboxWebhooks).to receive(:execute).and_return(OpenStruct.new(success?: true, data: {}))
    described_class.perform_now
    expect(Email::RenewMailboxWebhooks).to have_received(:execute)
  end
end
