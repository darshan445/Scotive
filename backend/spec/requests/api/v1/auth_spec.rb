# frozen_string_literal: true

require "rails_helper"

RSpec.describe "API v1 auth", type: :request do
  let(:email) { "ada@agency.com" }
  let(:password) { "password1" }

  def json_body
    JSON.parse(response.body)
  end

  def auth_headers(token)
    { "Authorization" => "Bearer #{token}" }
  end

  describe "POST /api/v1/auth/sign-up" do
    it "creates an owner, organization, and JWT" do
      post "/api/v1/auth/sign-up",
           params: { email: email, password: password, name: "Ada Lovelace" },
           as: :json

      expect(response).to have_http_status(:created)
      expect(json_body.dig("data", "token")).to be_present
      expect(json_body.dig("data", "user", "email")).to eq(email)
      expect(json_body.dig("data", "user", "role")).to eq("owner")
      expect(json_body.dig("data", "user", "first_name")).to eq("Ada")
      expect(json_body.dig("data", "user", "organization", "name")).to eq("Ada Lovelace's workspace")
    end

    it "rejects a short password" do
      post "/api/v1/auth/sign-up",
           params: { email: email, password: "short" },
           as: :json

      expect(response).to have_http_status(:unprocessable_content)
      expect(json_body["errors"].first["detail"]).to match(/at least 8/)
    end
  end

  describe "POST /api/v1/auth/sign-in" do
    before do
      Auth::SignUp.execute(email: email, password: password, name: "Ada")
    end

    it "returns a session" do
      post "/api/v1/auth/sign-in",
           params: { email: email, password: password },
           as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "token")).to be_present
      expect(json_body.dig("data", "user", "email")).to eq(email)
    end

    it "rejects a bad password" do
      post "/api/v1/auth/sign-in",
           params: { email: email, password: "wrong-password" },
           as: :json

      expect(response).to have_http_status(:unauthorized)
    end
  end

  describe "GET /api/v1/auth/me" do
    it "requires a token" do
      get "/api/v1/auth/me", as: :json
      expect(response).to have_http_status(:unauthorized)
    end

    it "returns the current user" do
      token = Auth::SignUp.execute(email: email, password: password, name: "Ada").data[:token]

      get "/api/v1/auth/me", headers: auth_headers(token), as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "user", "email")).to eq(email)
    end
  end

  describe "password reset" do
    before do
      Auth::SignUp.execute(email: email, password: password, name: "Ada")
    end

    it "emails a reset link and accepts the token" do
      expect {
        post "/api/v1/auth/forgot-password", params: { email: email }, as: :json
      }.to change { ActionMailer::Base.deliveries.size }.by(1)

      expect(response).to have_http_status(:ok)

      mail = ActionMailer::Base.deliveries.last
      token = mail.body.encoded[/token=([^&\s]+)/, 1]
      expect(token).to be_present

      post "/api/v1/auth/reset-password",
           params: { token: CGI.unescape(token), password: "newpass12" },
           as: :json

      expect(response).to have_http_status(:ok)

      post "/api/v1/auth/sign-in",
           params: { email: email, password: "newpass12" },
           as: :json
      expect(response).to have_http_status(:ok)
    end
  end

  describe "DELETE /api/v1/auth/sign-out" do
    it "revokes the JWT" do
      token = Auth::SignUp.execute(email: email, password: password, name: "Ada").data[:token]

      delete "/api/v1/auth/sign-out", headers: auth_headers(token), as: :json
      expect(response).to have_http_status(:no_content)

      get "/api/v1/auth/me", headers: auth_headers(token), as: :json
      expect(response).to have_http_status(:unauthorized)
    end
  end
end
