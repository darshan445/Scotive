# frozen_string_literal: true

require "rails_helper"

RSpec.describe Quickbooks::RefreshTokensJob, type: :job do
  it "runs the token refresh interactor" do
    allow(Quickbooks::RefreshTokens).to receive(:execute).and_return(OpenStruct.new(success?: true, data: {}))
    described_class.perform_now
    expect(Quickbooks::RefreshTokens).to have_received(:execute)
  end
end
