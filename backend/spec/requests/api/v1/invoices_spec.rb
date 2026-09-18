# frozen_string_literal: true

require "rails_helper"

RSpec.describe "API v1 invoice actions", type: :request do
  def json_body
    JSON.parse(response.body)
  end

  def auth_headers(token)
    { "Authorization" => "Bearer #{token}" }
  end

  it "marks an invoice paid for the current organization" do
    token = Auth::SignUp.execute(email: "ada@agency.com", password: "password1", name: "Ada").data[:token]
    user = User.find_by!(email: "ada@agency.com")
    organization = user.organization
    qbo = organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
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
      due_date: Date.new(2026, 9, 1),
      total_amount: 100,
      balance_remaining: 100,
      current_ar_status: "overdue"
    )

    post "/api/v1/invoices/#{invoice.id}/action",
         params: { action: "mark_paid" },
         headers: auth_headers(token),
         as: :json

    expect(response).to have_http_status(:ok)
    expect(json_body.dig("data", "action")).to eq("mark_paid")
    expect(invoice.reload.current_ar_status).to eq("paid")
  end

  it "requires a token" do
    post "/api/v1/invoices/00000000-0000-0000-0000-000000000000/action",
         params: { action: "mark_paid" },
         as: :json
    expect(response).to have_http_status(:unauthorized)
  end
end
