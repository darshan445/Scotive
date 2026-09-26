# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::EvaluateInvoiceState do
  include ActiveSupport::Testing::TimeHelpers

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
      primary_email: "ap@acme.com",
      domain: "acme.com"
    )
  end
  let(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-404",
      invoice_number: "INV-404",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 30),
      total_amount: 600,
      balance_remaining: 600
    )
  end

  def add_message!(id:, from:, to:, direction:, body:, sent_at: Time.utc(2026, 9, 16, 15), automatic: false)
    conversation = organization.conversations.find_by(integration_id: mailbox.id, external_thread_id: "t-home")
    if conversation.blank?
      conversation = organization.conversations.create!(
        integration: mailbox,
        external_thread_id: "t-home",
        subject: "INV-404"
      )
      InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    end
    conversation.messages.create!(
      external_message_id: id,
      direction: direction,
      from_address: from,
      to_addresses: [ to ],
      sent_at: sent_at,
      clean_body: body,
      automatic: automatic,
      is_anchor: direction == "user_to_client",
      created_at: Time.current
    )
  end

  it "pauses cadence on a human reply and does not write a promise status" do
    add_message!(id: "m-out", from: "owner@studio.com", to: "ap@acme.com", direction: "user_to_client", body: "Invoice attached")
    human = add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "I'll pay Friday")

    result = described_class.execute(invoice: invoice)
    expect(result.success?).to eq(true)
    expect(invoice.reload.chase_status).to eq("needs_you")
    expect(invoice.list_bucket).to eq("needs_you")
    expect(invoice.last_human_inbound_message_id).to eq(human.id)
    expect(invoice.invoice_chase_events.last.event_type).to eq("human_inbound")
    expect(invoice.books_status).to eq("open")
  end

  it "brings a sleeping invoice back to Needs you when the client writes again" do
    add_message!(id: "m-out", from: "owner@studio.com", to: "ap@acme.com", direction: "user_to_client", body: "Invoice attached")
    invoice.update!(chase_status: "watching", expected_pay_date: Date.new(2026, 9, 30))
    add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "Paying next week")

    result = described_class.execute(invoice: invoice)
    expect(result.success?).to eq(true)
    expect(invoice.reload.chase_status).to eq("needs_you")
    expect(invoice.expected_pay_date).to be_nil
    expect(invoice.list_bucket).to eq("needs_you")
  end

  it "ignores an out-of-office and stays in Watching" do
    add_message!(id: "m-out", from: "owner@studio.com", to: "ap@acme.com", direction: "user_to_client", body: "Invoice attached")
    add_message!(
      id: "m-ooo",
      from: "ap@acme.com",
      to: "owner@studio.com",
      direction: "client_to_user",
      body: "I am out of the office",
      automatic: true
    )

    result = described_class.execute(invoice: invoice)
    expect(result.success?).to eq(true)
    expect(invoice.reload.chase_status).to eq("watching")
    expect(invoice.invoice_chase_events.last.event_type).to eq("auto_reply_ignored")
  end

  it "skips paid invoices" do
    invoice.update!(books_status: "paid", balance_remaining: 0)
    result = described_class.execute(invoice: invoice)
    expect(result.data[:skipped]).to eq(true)
  end
end
