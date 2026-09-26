# frozen_string_literal: true

require "rails_helper"

RSpec.describe "API v1 ledger and clients", type: :request do
  let(:email) { "ada@agency.com" }
  let(:password) { "password1" }
  let!(:session) { Auth::SignUp.execute(email: email, password: password, name: "Ada") }
  let(:token) { session.data[:token] }
  let(:organization) { User.find_by!(email: email).organization }
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "at",
      connection_status: "connected"
    )
  end
  let(:client_row) do
    organization.clients.create!(
      integration: qbo,
      external_id: "1",
      name: "Acme Co",
      primary_email: "ap@acme.com",
      domain: "acme.com",
      associated_emails: [ "ap@acme.com" ]
    )
  end

  def auth_headers
    { "Authorization" => "Bearer #{token}" }
  end

  def json_body
    JSON.parse(response.body)
  end

  before do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-9",
      invoice_number: "INV-9",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 20),
      total_amount: 80,
      balance_remaining: 80,
      books_status: "open"
    )
  end

  it "requires auth for ledger" do
    get "/api/v1/ledger", as: :json
    expect(response).to have_http_status(:unauthorized)
  end

  it "returns ledger invoices" do
    get "/api/v1/ledger", headers: auth_headers, as: :json
    expect(response).to have_http_status(:ok)
    invoices = json_body.dig("data", "invoices")
    expect(invoices.first["invoice_ref"]).to eq("INV-9")
    expect(invoices.first["status"]).to eq("auto_reminders")
    expect(json_body.dig("data", "client_count")).to eq(1)
    expect(invoices.first["unmatched"]).to eq(true)
    expect(invoices.first["has_thread"]).to eq(false)
  end

  it "returns the clients list and detail" do
    get "/api/v1/clients", headers: auth_headers, as: :json
    expect(response).to have_http_status(:ok)
    expect(json_body.dig("data", "clients").first["email"]).to eq("ap@acme.com")

    get "/api/v1/clients/#{CGI.escape('ap@acme.com')}", headers: auth_headers, as: :json
    expect(response).to have_http_status(:ok)
    expect(json_body.dig("data", "name")).to eq("Acme Co")
    expect(json_body.dig("data", "invoices").first["invoice_ref"]).to eq("INV-9")
  end
end
