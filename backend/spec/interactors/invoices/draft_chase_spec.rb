# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoices::DraftChase do
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
      balance_remaining: 250,
      books_status: "open",
      pay_link_token: "https://pay.qbo.test/inv-12"
    )
  end
  let(:llm) { instance_double(Email::LlmClient) }

  def execute!(**extra)
    described_class.execute(organization: organization, invoice_id: invoice.id, client: llm, **extra)
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

  def add_inbound!(body)
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    message = conversation.messages.create!(
      external_message_id: "m-in",
      direction: "client_to_user",
      from_address: "ap@acme.com",
      to_addresses: [ "owner@studio.com" ],
      sent_at: Time.utc(2026, 9, 17, 15),
      created_at: Time.utc(2026, 9, 17, 15),
      clean_body: body
    )
    invoice.update!(last_human_inbound_at: message.sent_at, last_human_inbound_message: message, chase_status: "needs_you")
    conversation
  end

  it "drafts a chase and appends the formatted pay-link template" do
    add_home!
    allow(llm).to receive(:complete_json).and_return(
      "job" => "chase",
      "include_pay_link" => true,
      "reason" => "A payment reminder.",
      "subject" => "Re: INV-12",
      "body" => "Hi Acme, checking on INV-12.\n\nThanks"
    )

    result = execute!
    expect(result.success?).to eq(true)
    expect(result.data[:job]).to eq("chase")
    expect(result.data[:needs_instruction]).to eq(false)
    expect(result.data[:include_pay_link]).to eq(true)
    expect(result.data[:body]).to include("Hi Acme, checking on INV-12.")
    expect(result.data[:body]).not_to include("https://pay.qbo.test/inv-12")
    expect(result.data[:mail_preview][:pay_label]).to eq("View and pay this invoice")
    expect(result.data[:mail_preview][:include_pay_link]).to eq(true)
  end

  it "does not draft a decision until the owner instructs" do
    add_inbound!("Can you take $50 off this invoice?")
    allow(llm).to receive(:complete_json)

    result = execute!
    expect(result.success?).to eq(true)
    expect(result.data[:job]).to eq("decision")
    expect(result.data[:needs_instruction]).to eq(true)
    expect(result.data[:body]).to eq("")
    expect(result.data[:reason]).to include("change the amount")
    expect(llm).not_to have_received(:complete_json)
  end

  it "does not draft a chase when they asked for a W-9 even if the model would" do
    add_inbound!("Can you resend the W-9 for SIM-2306 before we put this on the pay run?")
    expect(llm).not_to receive(:complete_json)

    result = execute!
    expect(result.data[:job]).to eq("decision")
    expect(result.data[:needs_instruction]).to eq(true)
    expect(result.data[:body]).to eq("")
    expect(result.data[:reason]).to include("W-9")
    expect(result.data[:instruction_hint]).to include("W-9")
  end

  it "drafts a decision only from the owner instruction and skips the pay link" do
    add_inbound!("Can you take $50 off this invoice?")
    allow(llm).to receive(:complete_json).and_return(
      "job" => "decision",
      "include_pay_link" => false,
      "reason" => "Invoice stands.",
      "subject" => "Re: INV-12",
      "body" => "The balance is still $250.\n\nThanks"
    )

    result = execute!(note: "invoice stands")
    expect(result.success?).to eq(true)
    expect(result.data[:needs_instruction]).to eq(false)
    expect(result.data[:body]).to include("The balance is still $250.")
    expect(result.data[:body]).not_to include("https://pay.qbo.test/inv-12")
  end

  it "retries when an instruction comes back with an empty body" do
    add_inbound!("Can you resend the W-9 for SIM-2306 before we put this on the pay run?")
    allow(llm).to receive(:complete_json).and_return(
      { "job" => "decision", "include_pay_link" => false, "reason" => "", "subject" => "Re: INV-12", "body" => "" },
      {
        "job" => "decision",
        "include_pay_link" => false,
        "reason" => "W-9 is on the way.",
        "subject" => "Re: INV-12",
        "body" => "Hi Acme,\n\nThe W-9 is on the way for INV-12 so you can put this on the pay run.\n\nThanks\nAda"
      }
    )

    result = execute!(note: "it's on the way")
    expect(result.data[:body]).to include("W-9 is on the way")
    expect(result.data[:body]).to include("Hi Acme")
    expect(result.data[:needs_instruction]).to eq(false)
    expect(llm).to have_received(:complete_json).twice
  end

  it "does not tell the owner to shorten a note when the writer fails" do
    add_inbound!("Can you resend the W-9?")
    allow(llm).to receive(:complete_json).and_return(
      "job" => "decision",
      "include_pay_link" => false,
      "reason" => "",
      "subject" => "Re: INV-12",
      "body" => ""
    )

    result = execute!(note: "it's on the way")
    expect(result.data[:body]).to eq("")
    expect(result.data[:reason]).to eq("Couldn't write that reply. Try again.")
    expect(result.data[:reason]).not_to include("shorter")
  end

  it "falls back to a pending Firm draft when the LLM fails on a silent invoice" do
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    invoice.outbox_messages.create!(
      organization: organization,
      conversation: conversation,
      status: "draft",
      cadence_step: "firm_plus_7",
      to_address: "ap@acme.com",
      subject: "Re: INV-12",
      body: "Firm copy from cadence",
      scheduled_send_at: Time.current
    )

    result = execute!
    expect(result.success?).to eq(true)
    expect(result.data[:body]).to include("Firm copy from cadence")
    expect(result.data[:body]).not_to include("https://pay.qbo.test/inv-12")
    expect(result.data[:tone_label]).to eq("Firm follow-up")
    expect(result.data[:is_reply]).to eq(true)
    expect(result.data[:job]).to eq("chase")
  end

  it "does not guess a draft when the LLM fails after a client reply" do
    add_inbound!("Can you adjust this?")
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")

    result = execute!
    expect(result.success?).to eq(true)
    expect(result.data[:needs_instruction]).to eq(true)
    expect(result.data[:body]).to eq("")
    expect(result.data[:job]).to eq("decision")
  end

  it "falls back to status templates and prepends a steer note when the LLM fails" do
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")
    travel_to Time.utc(2026, 9, 18, 12) do
      result = execute!(note: "mention the PO")
      expect(result.success?).to eq(true)
      expect(result.data[:tone_label]).to eq("Firm follow-up")
      expect(result.data[:body]).to include("mention the PO")
      expect(result.data[:body]).to include("INV-12")
      expect(result.data[:include_pay_link]).to eq(true)
      expect(result.data[:body]).not_to include("https://pay.qbo.test/inv-12")
    end
  end

  it "uses saved last Friendly offset before Needs you drafts Firm" do
    add_home!
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")
    organization.update!(escalation_offsets: [ -3, 0, 20 ])
    travel_to Time.utc(2026, 9, 18, 12) do
      result = execute!
      expect(result.success?).to eq(true)
      expect(result.data[:tone_label]).to eq("Friendly reminder")
      expect(result.data[:cadence_step]).to eq("due_today")
    end
  end
end
