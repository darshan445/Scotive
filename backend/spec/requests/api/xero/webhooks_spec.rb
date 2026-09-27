# frozen_string_literal: true

require "rails_helper"
require "base64"
require "openssl"

RSpec.describe "POST /api/xero/webhooks", type: :request do
  let(:key) { "xero-webhook-test-key" }

  def sign(body)
    Base64.strict_encode64(OpenSSL::HMAC.digest("SHA256", key, body))
  end

  around do |example|
    prior = ENV["XERO_WEBHOOK_KEY"]
    ENV["XERO_WEBHOOK_KEY"] = key
    example.run
    ENV["XERO_WEBHOOK_KEY"] = prior
  end

  it "returns 200 with an empty body for a valid intent-to-receive" do
    body = { "events" => [], "firstEventSequence" => 0, "lastEventSequence" => 0 }.to_json

    post "/api/xero/webhooks", params: body, headers: { "CONTENT_TYPE" => "application/json", "X-Xero-Signature" => sign(body) }

    expect(response).to have_http_status(:ok)
    expect(response.body).to eq("")
    expect(WebhookEvent.count).to eq(0)
  end

  it "returns 401 with an empty body for a bad signature" do
    body = { "events" => [] }.to_json

    post "/api/xero/webhooks", params: body, headers: { "CONTENT_TYPE" => "application/json", "X-Xero-Signature" => "nope" }

    expect(response).to have_http_status(:unauthorized)
    expect(response.body).to eq("")
  end
end
