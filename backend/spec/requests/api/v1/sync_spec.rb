# frozen_string_literal: true

require "rails_helper"

RSpec.describe "API v1 sync", type: :request do
  include ActiveJob::TestHelper

  let(:email) { "ada@agency.com" }
  let(:password) { "password1" }
  let!(:session) { Auth::SignUp.execute(email: email, password: password, name: "Ada") }
  let(:token) { session.data[:token] }
  let(:organization) { User.find_by!(email: email).organization }

  def auth_headers
    { "Authorization" => "Bearer #{token}" }
  end

  def json_body
    JSON.parse(response.body)
  end

  after do
    clear_enqueued_jobs
    Sync::State.reset!
  end

  it "requires auth" do
    post "/api/v1/sync", as: :json
    expect(response).to have_http_status(:unauthorized)
  end

  it "accepts Sync Now and reports idle after the job" do
    post "/api/v1/sync", headers: auth_headers, as: :json
    expect(response).to have_http_status(:accepted)
    expect(json_body.dig("data", "accepted")).to eq(true)
    expect(json_body.dig("data", "sync_running")).to eq(true)
    expect(Sync::RunNowJob).to have_been_enqueued.with(organization.id)

    perform_enqueued_jobs
    get "/api/v1/sync", headers: auth_headers, as: :json
    expect(response).to have_http_status(:ok)
    expect(json_body.dig("data", "sync_running")).to eq(false)
  end
end
