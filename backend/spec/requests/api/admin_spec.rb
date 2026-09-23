# frozen_string_literal: true

require "rails_helper"

RSpec.describe "API admin", type: :request do
  def json_body
    JSON.parse(response.body)
  end

  around do |example|
    prior_email = ENV["ADMIN_EMAIL"]
    prior_password = ENV["ADMIN_PASSWORD"]
    ENV["ADMIN_EMAIL"] = "ops@scotive.test"
    ENV["ADMIN_PASSWORD"] = "secret123"
    example.run
  ensure
    ENV["ADMIN_EMAIL"] = prior_email
    ENV["ADMIN_PASSWORD"] = prior_password
  end

  def sign_in_admin!
    post "/api/admin/login", params: { email: "ops@scotive.test", password: "secret123" }, as: :json
    expect(response).to have_http_status(:ok)
  end

  it "rejects a bad password" do
    post "/api/admin/login", params: { email: "ops@scotive.test", password: "nope" }, as: :json
    expect(response).to have_http_status(:unauthorized)
  end

  it "requires sign-in for the dashboard" do
    get "/api/admin/dashboard", as: :json
    expect(response).to have_http_status(:unauthorized)
  end

  it "returns users, invoices, and contact messages after login" do
    signup = Auth::SignUp.execute(email: "ada@agency.com", password: "password1", name: "Ada Lovelace")
    organization = User.find_by!(email: "ada@agency.com").organization
    qbo = organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      connection_status: "connected"
    )
    mailbox = organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "owner@studio.com",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
    client_row = organization.clients.create!(
      integration: qbo,
      external_id: "1",
      name: "Acme",
      primary_email: "ap@acme.com"
    )
    invoice = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-12",
      invoice_number: "INV-12",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 15),
      total_amount: 250,
      balance_remaining: 250,
      books_status: "open"
    )
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-12",
      subject: "Invoice INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation.messages.create!(
      external_message_id: "msg-1",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ "ap@acme.com" ],
      sent_at: Time.utc(2026, 9, 1, 12),
      clean_body: "Please pay INV-12",
      is_anchor: true,
      created_at: Time.current
    )
    ContactMessage.create!(name: "Bo", email: "bo@studio.com", company: "Studio", message: "How does pause work?")

    sign_in_admin!

    get "/api/admin/me", as: :json
    expect(response).to have_http_status(:ok)
    expect(json_body.dig("data", "email")).to eq("ops@scotive.test")

    get "/api/admin/dashboard", as: :json
    expect(response).to have_http_status(:ok)
    expect(json_body.dig("data", "stats", "total_users")).to eq(1)
    expect(json_body.dig("data", "stats", "gmail_connected")).to eq(1)
    expect(json_body.dig("data", "stats", "qbo_connected")).to eq(1)
    user_row = json_body.dig("data", "users").first
    expect(user_row["email"]).to eq("ada@agency.com")
    expect(user_row["open_invoice_count"]).to eq(1)

    get "/api/admin/users/#{user_row['id']}/invoices", as: :json
    expect(response).to have_http_status(:ok)
    row = json_body.dig("data", "invoices").first
    expect(row["invoice_ref"]).to eq("INV-12")
    expect(row["source"]).to eq("qbo")
    expect(row["evidence_sentence"]).to include("INV-12")

    get "/api/admin/contact-messages", as: :json
    expect(response).to have_http_status(:ok)
    message = json_body.dig("data", "messages").first
    expect(message["email"]).to eq("bo@studio.com")
    expect(message["status"]).to eq("new")

    post "/api/admin/contact-messages/#{message['id']}/read", as: :json
    expect(response).to have_http_status(:ok)
    expect(ContactMessage.find(message["id"]).status).to eq("read")

    post "/api/admin/logout", as: :json
    expect(response).to have_http_status(:no_content)
    get "/api/admin/dashboard", as: :json
    expect(response).to have_http_status(:unauthorized)
    expect(signup.success?).to eq(true)
  end
end
