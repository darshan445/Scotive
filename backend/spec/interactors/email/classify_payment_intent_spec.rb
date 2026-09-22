# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::ClassifyPaymentIntent do
  let(:llm) { instance_double(Email::LlmClient) }

  it "returns invoice_payment when the reader says so" do
    allow(llm).to receive(:complete_json).and_return("intent" => "invoice_payment")

    result = described_class.execute(subject: "Payment", body: "We will pay both invoices.", client: llm)

    expect(result).to be_success
    expect(result.data[:intent]).to eq("invoice_payment")
  end

  it "keeps other_payment when the reader says the money is not this vendor's invoice" do
    allow(llm).to receive(:complete_json).and_return("intent" => "other_payment")

    result = described_class.execute(
      subject: "Quote for the spring add-on",
      body: "Can you send a new estimate? Budget for next quarter is about $4,000.",
      client: llm
    )

    expect(result).to be_success
    expect(result.data[:intent]).to eq("other_payment")
  end

  it "coerces unknown intents to unrelated" do
    allow(llm).to receive(:complete_json).and_return("intent" => "promised")

    result = described_class.execute(subject: "Hi", body: "Hello", client: llm)

    expect(result).to be_success
    expect(result.data[:intent]).to eq("unrelated")
  end

  it "fails when the reader cannot return JSON" do
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")

    result = described_class.execute(subject: "Hi", body: "Hello", client: llm)

    expect(result).not_to be_success
  end
end
