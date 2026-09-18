# frozen_string_literal: true

require "rails_helper"

RSpec.describe Contacts::Create do
  it "stores a public contact message" do
    result = described_class.execute(
      name: "Ada",
      email: "ada@studio.com",
      company: "Studio",
      message: "How does cadence pause on a reply?"
    )
    expect(result.success?).to eq(true)
    expect(ContactMessage.sole.email).to eq("ada@studio.com")
  end

  it "accepts honeypot submissions without persisting" do
    result = described_class.execute(
      name: "Bot",
      email: "bot@spam.test",
      company: nil,
      message: "spam",
      website: "https://spam.test"
    )
    expect(result.success?).to eq(true)
    expect(ContactMessage.count).to eq(0)
  end
end
