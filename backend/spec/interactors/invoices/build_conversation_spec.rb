# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoices::BuildConversation do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let!(:mailbox) do
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "owner@studio.com",
      connection_status: "connected"
    )
  end
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      connection_status: "connected"
    )
  end
  let(:client_row) do
    organization.clients.create!(
      integration: qbo,
      external_id: "1",
      name: "Acme",
      primary_email: "ap@acme.com"
    )
  end
  let(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "SIM-2102",
      invoice_number: "SIM-2102",
      issue_date: Date.new(2026, 9, 1),
      due_date: Date.new(2026, 10, 1),
      total_amount: 500,
      balance_remaining: 500,
      current_ar_status: "promised"
    )
  end

  def add_thread!(external_id, subject, primary:, messages:)
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: external_id,
      subject: subject
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: primary, created_at: Time.current)
    messages.each do |row|
      conversation.messages.create!(
        external_message_id: row[:id],
        direction: row[:direction],
        from_address: row[:from],
        to_addresses: [ "ap@acme.com" ],
        sent_at: row[:sent_at],
        clean_body: row[:body],
        created_at: Time.current
      )
    end
    conversation
  end

  it "returns a newest-first conversation from every linked thread" do
    add_thread!(
      "t-wire",
      "Status of wire transfer for SIM-2102",
      primary: false,
      messages: [
        {
          id: "m-wire",
          direction: "client_to_user",
          from: "ap@acme.com",
          sent_at: 1.hour.ago,
          body: "Can you confirm whether the wire hit your account?"
        }
      ]
    )
    add_thread!(
      "t-home",
      "Invoice SIM-2102 from Studio",
      primary: true,
      messages: [
        {
          id: "m-send",
          direction: "user_to_client",
          from: "owner@studio.com",
          sent_at: 3.hours.ago,
          body: "Your invoice is attached."
        },
        {
          id: "m-sent-claim",
          direction: "client_to_user",
          from: "ap@acme.com",
          sent_at: 2.hours.ago,
          body: "Wire sent just now!"
        }
      ]
    )

    result = described_class.execute(organization: organization, invoice_id: invoice.id)

    expect(result).to be_success
    expect(result.data[:thread_id]).to eq("t-home")
    expect(result.data[:threads].map { |row| [ row[:thread_id], row[:is_primary] ] }).to eq(
      [ [ "t-home", true ], [ "t-wire", false ] ]
    )
    expect(result.data[:messages].map { |row| row[:body] }).to eq(
      [
        "Can you confirm whether the wire hit your account?",
        "Wire sent just now!",
        "Your invoice is attached."
      ]
    )
    expect(result.data[:client_ever_replied]).to eq(true)
    expect(result.data[:threads].last[:messages].first[:body]).to include("confirm whether the wire")
  end

  it "hides a Unipile/Gmail twin of the same send" do
    sent_at = Time.utc(2026, 9, 22, 6, 57, 43)
    add_thread!(
      "t-home",
      "Invoice 1064",
      primary: true,
      messages: [
        {
          id: "GdrFaK8zU_yokzYExXyqLA",
          direction: "user_to_client",
          from: "owner@studio.com",
          sent_at: sent_at,
          body: "Your invoice is attached."
        },
        {
          id: "1a0c7e7f9b9a7a1c",
          direction: "user_to_client",
          from: "owner@studio.com",
          sent_at: sent_at,
          body: "Your invoice is attached."
        }
      ]
    )

    result = described_class.execute(organization: organization, invoice_id: invoice.id)

    expect(result).to be_success
    expect(result.data[:messages].map { |row| row[:body] }).to eq([ "Your invoice is attached." ])
  end

  it "returns empty threads when nothing is linked" do
    result = described_class.execute(organization: organization, invoice_id: invoice.id)

    expect(result).to be_success
    expect(result.data[:threads]).to eq([])
    expect(result.data[:messages]).to eq([])
    expect(result.data[:thread_id]).to eq(nil)
  end
end
