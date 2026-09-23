# frozen_string_literal: true

require "rails_helper"

RSpec.describe "API v1 integrations OAuth", type: :request do
  let(:email) { "ada@agency.com" }
  let(:password) { "password1" }
  let!(:signup) { Auth::SignUp.execute(email: email, password: password, name: "Ada") }
  let(:token) { signup.data[:token] }
  let(:organization) { User.find_by!(email: email).organization }

  def json_body
    JSON.parse(response.body)
  end

  def auth_headers
    { "Authorization" => "Bearer #{token}" }
  end

  describe "GET /api/v1/qbo/oauth/start" do
    it "requires a token" do
      get "/api/v1/qbo/oauth/start", as: :json
      expect(response).to have_http_status(:unauthorized)
    end

    it "returns an Intuit authorization URL" do
      get "/api/v1/qbo/oauth/start", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      url = json_body.dig("data", "authorization_url")
      expect(url).to include("https://appcenter.intuit.com/connect/oauth2")
      expect(url).to include("client_id=")
      expect(url).to include("state=")
    end
  end

  describe "GET /api/qbo/oauth/callback" do
    let(:qbo_client) { instance_double(Quickbooks::QuickbookClient) }

    before do
      allow(Quickbooks::QuickbookClient).to receive(:new).and_return(qbo_client)
      allow(qbo_client).to receive(:exchange_code).and_return(
        "access_token" => "at-1",
        "refresh_token" => "rt-1",
        "expires_in" => 3600
      )
      allow(qbo_client).to receive(:get_company_info).and_return(
        "CompanyInfo" => { "CompanyName" => "Acme Ops" }
      )
    end

    it "persists the QBO integration and redirects to the frontend" do
      state = Rails.application.message_verifier("oauth").generate(
        { "organization_id" => organization.id, "provider" => "qbo" },
        expires_in: 15.minutes,
        purpose: :oauth
      )

      get "/api/qbo/oauth/callback", params: { code: "auth-code", realmId: "realm-99", state: state }

      expect(response).to redirect_to(%r{/dashboard\?qbo=connected})
      integration = organization.integrations.accounting.find_by(provider: "qbo")
      expect(integration).to be_connected
      expect(integration.external_account_id).to eq("realm-99")
      expect(integration.account_name).to eq("Acme Ops")
      expect(integration.access_token).to eq("at-1")
    end

    it "maps Intuit denial to qbo=access_denied" do
      get "/api/qbo/oauth/callback", params: { error: "access_denied", state: "x" }

      expect(response).to redirect_to(%r{qbo=access_denied})
    end

    it "redirects with qbo=error when company info fails after token exchange" do
      allow(qbo_client).to receive(:get_company_info).and_raise(
        Faraday::Error, "QBO company info failed (401): message=AuthenticationFailed; errorCode=003200; statusCode=401"
      )
      state = Rails.application.message_verifier("oauth").generate(
        { "organization_id" => organization.id, "provider" => "qbo" },
        expires_in: 15.minutes,
        purpose: :oauth
      )

      get "/api/qbo/oauth/callback", params: { code: "auth-code", realmId: "realm-99", state: state }

      expect(response).to redirect_to(%r{qbo=error})
      expect(organization.integrations.accounting.find_by(provider: "qbo")).to be_blank
    end
  end

  describe "GET /api/v1/qbo/status" do
    it "returns disconnected when nothing is stored" do
      get "/api/v1/qbo/status", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "connected")).to eq(false)
      expect(json_body.dig("data", "import_progress", "status")).to eq("idle")
    end

    it "does not treat JWT auth as a new Devise sign-in" do
      user = User.find_by!(email: email)
      count_before = user.sign_in_count

      2.times { get "/api/v1/qbo/status", headers: auth_headers, as: :json }

      expect(response).to have_http_status(:ok)
      expect(user.reload.sign_in_count).to eq(count_before)
    end
  end

  describe "GET /api/v1/gmail/oauth/start" do
    let(:email_client) { instance_double(Email::EmailClient) }

    it "returns a Unipile hosted auth URL" do
      allow(Email::EmailClient).to receive(:new).and_return(email_client)
      allow(email_client).to receive(:create_hosted_auth_link).and_return(
        "object" => "HostedAuthURL",
        "url" => "https://account.unipile.com/hosted"
      )

      get "/api/v1/gmail/oauth/start",
          headers: auth_headers,
          params: { provider: "google" }

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "authorization_url")).to eq("https://account.unipile.com/hosted")
      expect(email_client).to have_received(:create_hosted_auth_link).with(
        hash_including("providers" => [ "GOOGLE" ], "type" => "create")
      )
    end
  end

  describe "GET /api/v1/gmail/oauth/callback" do
    let(:email_client) { instance_double(Email::EmailClient) }

    it "persists a gmail integration and redirects" do
      allow(Email::EmailClient).to receive(:new).and_return(email_client)
      allow(email_client).to receive(:get_account).and_return(
        "id" => "acc-1",
        "type" => "GOOGLE",
        "name" => "ada@agency.com"
      )
      allow(email_client).to receive(:list_webhooks).and_return({ "items" => [] })
      allow(email_client).to receive(:create_webhook).and_return({ "id" => "wh-1" })

      state = Rails.application.message_verifier("oauth").generate(
        { "organization_id" => organization.id, "provider" => "gmail" },
        expires_in: 15.minutes,
        purpose: :oauth
      )

      get "/api/v1/gmail/oauth/callback", params: { account_id: "acc-1", state: state }

      expect(response).to redirect_to(%r{mail=connected})
      integration = organization.integrations.mailbox.find_by(provider: "gmail")
      expect(integration).to be_connected
      expect(integration.external_account_id).to eq("acc-1")
      expect(integration.account_name).to eq("ada@agency.com")
      expect(integration.webhook_subscription_id).to eq("wh-1")
    end
  end

  describe "GET /api/v1/onboarding/state" do
    it "stays on connections until invoices are imported" do
      organization.integrations.create!(
        category: "accounting",
        provider: "qbo",
        external_account_id: "realm-1",
        account_name: "Acme",
        connection_status: "connected"
      )

      get "/api/v1/onboarding/state", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "phase")).to eq("connections")
      expect(json_body.dig("data", "qbo_connected")).to eq(true)
      expect(json_body.dig("data", "gmail_connected")).to eq(false)
      expect(json_body.dig("data", "last_invoice_import_at")).to be_nil
    end

    it "stays on connections until mailbox threads are matched" do
      organization.integrations.create!(
        category: "accounting",
        provider: "qbo",
        external_account_id: "realm-1",
        account_name: "Acme",
        connection_status: "connected",
        last_synced_at: Time.current
      )
      organization.integrations.create!(
        category: "mailbox",
        provider: "gmail",
        external_account_id: "acc-1",
        account_name: "ada@agency.com",
        connection_status: "connected"
      )

      get "/api/v1/onboarding/state", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "phase")).to eq("connections")
      expect(json_body.dig("data", "gmail_connected")).to eq(true)
      expect(json_body.dig("data", "qbo_pipeline")).to be_nil
      expect(json_body.dig("data", "onboarding_modal_dismissed")).to eq(false)
    end
  end

  describe "POST /api/v1/onboarding/dismiss-modal" do
    it "persists the cadence explainer as dismissed" do
      expect(organization.onboarding_modal_dismissed).to eq(false)

      post "/api/v1/onboarding/dismiss-modal", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "onboarding_modal_dismissed")).to eq(true)
      expect(organization.reload.onboarding_modal_dismissed).to eq(true)
    end
  end

  describe "POST /api/v1/qbo/import" do
    it "imports open invoices and sets last_synced_at" do
      organization.integrations.create!(
        category: "accounting",
        provider: "qbo",
        external_account_id: "realm-1",
        account_name: "Acme",
        access_token: "at",
        refresh_token: "rt",
        token_expires_at: 1.hour.from_now,
        connection_status: "connected"
      )
      qbo_client = instance_double(Quickbooks::QuickbookClient)
      allow(Quickbooks::QuickbookClient).to receive(:new).and_return(qbo_client)
      allow(qbo_client).to receive(:query_open_invoices).and_return([])
      allow(qbo_client).to receive(:query_customers).and_return([])

      post "/api/v1/qbo/import", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "counts", "fetched")).to eq(0)
      expect(organization.integrations.find_by(provider: "qbo").reload.last_synced_at).to be_present
    end
  end

  describe "POST /api/v1/qbo/match-conversations" do
    it "matches mailbox threads and returns a completed pipeline" do
      organization.integrations.create!(
        category: "accounting",
        provider: "qbo",
        external_account_id: "realm-1",
        account_name: "Acme",
        connection_status: "connected",
        last_synced_at: Time.current
      )
      organization.integrations.create!(
        category: "mailbox",
        provider: "gmail",
        external_account_id: "acc-1",
        account_name: "ada@agency.com",
        connection_status: "connected"
      )
      email_client = instance_double(Email::EmailClient)
      allow(Email::EmailClient).to receive(:new).and_return(email_client)
      allow(email_client).to receive(:list_emails).and_return({ "items" => [] })

      post "/api/v1/qbo/match-conversations", headers: auth_headers, as: :json

      expect(response).to have_http_status(:ok)
      expect(json_body.dig("data", "queued")).to eq(false)
      expect(json_body.dig("data", "pipeline", "status")).to eq("complete")
      expect(organization.integrations.find_by(provider: "gmail").reload.sync_cursor).to eq("empty")
    end
  end
end
