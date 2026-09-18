# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::MorningJob, type: :job do
  it "delegates to Cadence::Morning" do
    allow(Cadence::Morning).to receive(:execute).and_return(OpenStruct.new(success?: true, data: { ran: 0 }))
    described_class.perform_now
    expect(Cadence::Morning).to have_received(:execute)
  end
end
