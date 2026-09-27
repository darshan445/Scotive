# frozen_string_literal: true

require "rails_helper"

RSpec.describe Xero::RefreshTokensJob, type: :job do
  it "delegates to Xero::RefreshTokens" do
    allow(Xero::RefreshTokens).to receive(:execute).and_return(OpenStruct.new(success?: true, data: {}))
    described_class.perform_now
    expect(Xero::RefreshTokens).to have_received(:execute)
  end
end
