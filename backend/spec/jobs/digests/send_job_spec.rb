# frozen_string_literal: true

require "rails_helper"

RSpec.describe Digests::SendJob, type: :job do
  it "delegates to Digests::Send" do
    allow(Digests::Send).to receive(:execute).and_return(OpenStruct.new(success?: true, data: { sent: 0 }))
    described_class.perform_now
    expect(Digests::Send).to have_received(:execute)
  end
end
