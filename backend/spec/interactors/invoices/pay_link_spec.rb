# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoices::PayLink do
  describe ".stored_token" do
    it "keeps a full pay URL so mail and drafts share the same identity" do
      url = "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=a1b2c3d4-e5f6-4780-ab12-cdef34567890"

      expect(described_class.stored_token(url)).to eq(url)
    end

    it "does not store a generic last path when the URL is blank" do
      expect(described_class.stored_token(nil)).to be_nil
      expect(described_class.stored_token("")).to be_nil
    end

    it "keeps a pre-extracted distinctive token" do
      expect(described_class.stored_token("paytok-2116")).to eq("paytok-2116")
    end
  end

  describe ".match?" do
    let(:qbo_url) { "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=a1b2c3d4-e5f6-4780-ab12-cdef34567890" }

    it "matches the full stored URL in the body" do
      expect(described_class.match?(qbo_url, "Pay here: #{qbo_url}")).to eq(true)
    end

    it "matches a unique jobId even when the rest of the URL is rewritten" do
      haystack = "Pay https://www.google.com/url?q=#{CGI.escape(qbo_url)}"

      expect(described_class.match?(qbo_url, haystack)).to eq(true)
    end

    it "matches an older last-path token inside a URL" do
      expect(described_class.match?("paytok-2116", "https://connect.intuit.com/pay/paytok-2116")).to eq(true)
    end

    it "does not treat generic path words as an identity" do
      expect(described_class.match?("invoice", "Please pay this invoice today")).to eq(false)
      expect(described_class.match?("pay", "Can you pay Friday?")).to eq(false)
    end
  end

  describe ".search_terms" do
    it "searches a unique query id, not CommerceNetwork" do
      url = "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=a1b2c3d4-e5f6-4780-ab12-cdef34567890"

      expect(described_class.search_terms(url)).to eq([ "a1b2c3d4-e5f6-4780-ab12-cdef34567890" ])
    end

    it "falls back to a numbered path segment" do
      url = "https://pay.example.com/inv/INV-101"

      expect(described_class.search_terms(url)).to eq([ "INV-101" ])
    end

    it "searches a txnId query when the path is generic" do
      url = "https://qbo.intuit.com/app/invoice?txnId=534"

      expect(described_class.search_terms(url)).to eq([ "txnId=534" ])
    end
  end

  describe ".urls_in" do
    it "keeps href targets that sanitize_body would strip" do
      html = '<a href="https://connect.intuit.com/pay/paytok-2116">View and pay</a>'

      expect(described_class.urls_in(html)).to include("https://connect.intuit.com/pay/paytok-2116")
    end
  end
end
