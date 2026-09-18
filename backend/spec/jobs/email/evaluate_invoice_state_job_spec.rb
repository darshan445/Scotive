# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::EvaluateInvoiceStateJob, type: :job do
  it "noops when the invoice is missing" do
    expect { described_class.perform_now("00000000-0000-0000-0000-000000000000") }.not_to raise_error
  end
end
