# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoices::ClassifyDraftJob do
  let(:organization) { Organization.create!(name: "Ada's workspace") }
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
  let!(:mailbox) do
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "owner@studio.com",
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
      external_id: "INV-12",
      invoice_number: "INV-12",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 4),
      total_amount: 250,
      balance_remaining: 250
    )
  end

  def add_home!
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation
  end

  def add_inbound!(body, sent_at: Time.utc(2026, 9, 17, 15))
    conversation = add_home!
    message = conversation.messages.create!(
      external_message_id: "m-in",
      direction: "client_to_user",
      from_address: "ap@acme.com",
      to_addresses: [ "owner@studio.com" ],
      sent_at: sent_at,
      created_at: sent_at,
      clean_body: body
    )
    invoice.update!(last_human_inbound_at: sent_at, last_human_inbound_message: message, chase_status: "needs_you")
    message
  end

  def classify
    described_class.execute(invoice: invoice)
  end

  it "chases a silent invoice that already has a HOME thread" do
    add_home!
    result = classify
    expect(result.data[:job]).to eq("chase")
    expect(result.data[:hold]).to eq(false)
  end

  it "holds when nothing is linked" do
    result = classify
    expect(result.data[:job]).to eq("decision")
    expect(result.data[:hold]).to eq(true)
  end

  it "holds while a check-back date is still in the future" do
    add_home!
    invoice.update!(chase_status: "watching", expected_pay_date: Date.current + 3)
    result = classify
    expect(result.data[:job]).to eq("decision")
    expect(result.data[:hold]).to eq(true)
    expect(result.data[:reason]).to include("Waiting until")
  end

  it "does not chase a W-9 request" do
    add_inbound!("Can you resend the W-9 for SIM-2306 before we put this on the pay run?")
    result = classify
    expect(result.data[:job]).to eq("decision")
    expect(result.data[:reason]).to include("W-9")
  end

  it "does not chase a says-paid claim" do
    add_inbound!("We already paid INV-12 last Tuesday.")
    expect(classify.data[:job]).to eq("decision")
  end

  it "does not chase an amount cut" do
    add_inbound!("Hold on. Take $400 off so this is $2000?")
    expect(classify.data[:reason]).to include("change the amount")
    expect(classify.data[:job]).to eq("decision")
  end

  it "does not chase a promise" do
    add_inbound!("Thanks — we have this scheduled and will pay Friday.")
    expect(classify.data[:job]).to eq("decision")
    expect(classify.data[:reason]).to include("check-back")
  end

  it "answers how-to-pay from the invoice" do
    add_inbound!("How do I pay this? Can you send the payment link?")
    expect(classify.data[:job]).to eq("answer_facts")
  end

  it "uses broken_date after a check-back expires" do
    add_home!
    invoice.update!(expected_pay_date: Date.current - 1, last_human_inbound_at: 2.days.ago)
    result = classify
    expect(result.data[:job]).to eq("broken_date")
  end
end
