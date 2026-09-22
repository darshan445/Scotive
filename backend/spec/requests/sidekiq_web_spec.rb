# frozen_string_literal: true

require "rails_helper"

RSpec.describe "Sidekiq Web", type: :request do
  it "serves the dashboard" do
    get "/sidekiq"
    follow_redirect! while response.redirect?

    expect(response).to have_http_status(:ok)
    expect(response.body).to match(/Sidekiq/i)
  end
end
