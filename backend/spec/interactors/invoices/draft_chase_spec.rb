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
      current_ar_status: "overdue",
      pay_link_token: "https://pay.qbo.test/inv-12"
    )
  end
  let(:llm) { instance_double(Email::LlmClient) }

  def execute!(**extra)
    described_class.execute(organization: organization, invoice_id: invoice.id, client: llm, **extra)
  end

  it "uses LLM copy when the reader returns a body" do
    allow(llm).to receive(:complete_json).and_return(
      "subject" => "Re: INV-12",
      "body" => "Hi Acme, checking on INV-12."
    )

    result = execute!
    expect(result.success?).to eq(true)
    expect(result.data[:body]).to eq("Hi Acme, checking on INV-12.")
    expect(result.data[:subject]).to eq("Re: INV-12")
    expect(llm).to have_received(:complete_json).with(hash_including(temperature: 0.3))
  end

  it "falls back to a pending Firm draft when the LLM fails" do
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
    expect(result.data[:body]).to eq("Firm copy from cadence")
    expect(result.data[:tone_label]).to eq("Firm follow-up")
    expect(result.data[:is_reply]).to eq(false)
  end

  it "falls back to status templates and prepends a steer note when the LLM fails" do
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")
    travel_to Time.utc(2026, 9, 18, 12) do
      result = execute!(note: "mention the PO")
      expect(result.success?).to eq(true)
      expect(result.data[:tone_label]).to eq("Final notice")
      expect(result.data[:body]).to include("mention the PO")
      expect(result.data[:body]).to include("INV-12")
      expect(result.data[:body]).to include("Pay here: https://pay.qbo.test/inv-12")
    end
  end

  it "uses saved ladder offsets to pick Firm before the follow-up interval" do
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")
    organization.update!(escalation_offsets: [ -3, 0, 7, 12 ], follow_up_interval_days: 10)
    travel_to Time.utc(2026, 9, 18, 12) do
      result = execute!
      expect(result.success?).to eq(true)
      expect(result.data[:tone_label]).to eq("Firm follow-up")
      expect(result.data[:cadence_step]).to eq("firm_plus_7")
    end
  end
end
