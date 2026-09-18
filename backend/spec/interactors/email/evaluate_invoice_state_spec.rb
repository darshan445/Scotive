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
      domain: "acme.com",
      associated_emails: [ "ap@acme.com", "cpa@books.com" ]
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
      balance_remaining: 600,
      current_ar_status: "invoiced"
    )
  end
  let(:llm) { instance_double(Email::LlmClient) }

  def add_message!(id:, from:, to:, direction:, body:, sent_at: Time.utc(2026, 9, 16, 15))
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
      cc_addresses: [],
      sent_at: sent_at,
      clean_body: body,
      is_anchor: direction == "user_to_client",
      created_at: Time.current
    )
  end

  def reader_result(status:, needs_reply: false, events: [], disputed: nil, promise_date: nil)
    {
      "status" => status,
      "needs_reply" => needs_reply,
      "promise_date" => promise_date,
      "disputed_claim_amount" => disputed,
      "new_events" => events
    }
  end

  it "commits a Friday promise, resolves the calendar date, and writes the ledger" do
    travel_to Time.utc(2026, 9, 18, 12) do
      add_message!(id: "m-out", from: "owner@studio.com", to: "ap@acme.com", direction: "user_to_client", body: "Invoice attached", sent_at: Time.utc(2026, 9, 1, 10))
      add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "I'll pay Friday")
      allow(llm).to receive(:complete_json).and_return(reader_result(
        status: "promised",
        events: [ {
          "type" => "promise",
          "message_id" => "m-in",
          "sender" => "client",
          "quote" => "I'll pay Friday",
          "data" => { "relative_phrase" => "Friday", "anchor_date" => "2026-09-16" },
          "confidence" => 0.91
        } ]
      ))

      result = described_class.execute(invoice: invoice, client: llm)

      expect(result).to be_success
      expect(result.data[:skipped]).to eq(false)
      expect(invoice.reload.current_ar_status).to eq("promised")
      expect(invoice.active_promise_date).to eq(Date.new(2026, 9, 18))
      expect(invoice.needs_reply).to eq(false)
      expect(invoice.invoice_state_transitions.last.trigger_source).to eq("ai_reader")
      expect(invoice.invoice_events.last.event_type).to eq("promise")
      expect(invoice.invoice_events.last.message.external_message_id).to eq("m-in")
      expect(Message.where(processed_by_ai: true).count).to eq(2)
      expect(llm).to have_received(:complete_json) do |system:, user:|
        payload = JSON.parse(user)
        expect(system).to include("platform conversation-state reader")
        expect(payload.dig("tracked_state", "status")).to eq("invoiced")
        expect(payload.dig("tracked_state", "promise_date")).to be_nil
        expect(payload["messages"].map { |row| row["id"] }).to eq(%w[m-out m-in])
      end
    end
  end

  it "marks a past promise as broken_promise" do
    travel_to Time.utc(2026, 9, 18, 12) do
      add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "Paying last Friday")
      allow(llm).to receive(:complete_json).and_return(reader_result(
        status: "promised",
        events: [ {
          "type" => "promise",
          "message_id" => "m-in",
          "sender" => "client",
          "quote" => "Paying last Friday",
          "data" => { "date" => "2026-09-11" }
        } ]
      ))

      result = described_class.execute(invoice: invoice, client: llm)

      expect(result).to be_success
      expect(invoice.reload.current_ar_status).to eq("broken_promise")
      expect(invoice.active_promise_date).to eq(Date.new(2026, 9, 11))
    end
  end

  it "sets disputed + needs_reply without changing books amounts" do
    add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "We only owe $400. Which account?")
    allow(llm).to receive(:complete_json).and_return(reader_result(
      status: "disputed",
      needs_reply: true,
      disputed: 400,
      events: [
        { "type" => "dispute", "message_id" => "m-in", "sender" => "client", "quote" => "We only owe $400", "data" => { "amount" => 400 } },
        { "type" => "needs_reply", "message_id" => "m-in", "sender" => "client", "quote" => "Which account?", "data" => {} }
      ]
    ))

    result = described_class.execute(invoice: invoice, client: llm)

    expect(result).to be_success
    expect(invoice.reload.current_ar_status).to eq("disputed")
    expect(invoice.needs_reply).to eq(true)
    expect(invoice.disputed_claim_amount).to eq(400)
    expect(invoice.balance_remaining).to eq(600)
    expect(invoice.invoice_events.count).to eq(2)
  end

  it "skips outbound-only threads and paid invoices" do
    add_message!(id: "m-out", from: "owner@studio.com", to: "ap@acme.com", direction: "user_to_client", body: "Invoice attached")
    allow(llm).to receive(:complete_json)

    result = described_class.execute(invoice: invoice, client: llm)

    expect(result).to be_success
    expect(result.data[:skipped]).to eq(true)
    expect(llm).not_to have_received(:complete_json)

    invoice.update!(current_ar_status: "paid", balance_remaining: 0)
    add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "Paid")
    paid = described_class.execute(invoice: invoice.reload, client: llm)
    expect(paid.data[:skipped]).to eq(true)
  end

  it "fails when the reader cannot return JSON" do
    add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "I'll pay Friday")
    allow(llm).to receive(:complete_json).and_raise(Faraday::Error, "timeout")

    result = described_class.execute(invoice: invoice, client: llm)

    expect(result).not_to be_success
    expect(result.errors.to_s).to include("State reader failed")
    expect(invoice.reload.current_ar_status).to eq("invoiced")
  end
end
