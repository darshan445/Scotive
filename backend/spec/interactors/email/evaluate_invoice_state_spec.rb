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

  def add_message!(id:, from:, to:, direction:, body:, sent_at: Time.utc(2026, 9, 16, 15), thread_id: "t-home")
    conversation = organization.conversations.find_by(integration_id: mailbox.id, external_thread_id: thread_id)
    if conversation.blank?
      conversation = organization.conversations.create!(
        integration: mailbox,
        external_thread_id: thread_id,
        subject: thread_id == "t-home" ? "INV-404" : thread_id
      )
      InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: thread_id == "t-home", created_at: Time.current)
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

  it "falls back to clock status when the reader returns promised with no date" do
    invoice.update!(due_date: Date.new(2026, 9, 14), current_ar_status: "overdue")
    add_message!(id: "m-in", from: "ap@acme.com", to: "owner@studio.com", direction: "client_to_user", body: "Can you confirm the wire?")
    allow(llm).to receive(:complete_json).and_return(reader_result(
      status: "promised",
      needs_reply: true,
      events: [ {
        "type" => "needs_reply",
        "message_id" => "m-in",
        "sender" => "client",
        "quote" => "Can you confirm the wire?"
      } ]
    ))

    travel_to Time.utc(2026, 9, 19, 12) do
      result = described_class.execute(invoice: invoice, client: llm)

      expect(result).to be_success
      expect(invoice.reload.current_ar_status).to eq("overdue")
      expect(invoice.active_promise_date).to be_nil
      expect(invoice.needs_reply).to eq(true)
    end
  end

  it "restores a standing Friday after the owner settles the amount dispute" do
    travel_to Time.utc(2026, 9, 19, 12) do
      invoice.update!(due_date: Date.new(2026, 9, 14), current_ar_status: "overdue", total_amount: 1000, balance_remaining: 1000)
      add_message!(
        id: "m-out",
        from: "owner@studio.com",
        to: "ap@acme.com",
        direction: "user_to_client",
        body: "Your invoice is attached.",
        sent_at: Time.utc(2026, 9, 19, 9, 38)
      )
      add_message!(
        id: "m-friday",
        from: "ap@acme.com",
        to: "owner@studio.com",
        direction: "client_to_user",
        body: "Thanks for the reminder. We have scheduled this and will pay this Friday.",
        sent_at: Time.utc(2026, 9, 19, 9, 48)
      )
      add_message!(
        id: "m-dispute",
        from: "ap@acme.com",
        to: "owner@studio.com",
        direction: "client_to_user",
        body: "Wait, stop the payment! Line item 2 says $400 for consulting, but our agreed rate was $200. We only owe $800.",
        sent_at: Time.utc(2026, 9, 19, 9, 49)
      )
      add_message!(
        id: "m-accept",
        from: "owner@studio.com",
        to: "ap@acme.com",
        direction: "user_to_client",
        body: "Confirmed, $800 it is. I have applied a $200 credit memo to reflect our agreement.",
        sent_at: Time.utc(2026, 9, 19, 9, 50)
      )
      allow(llm).to receive(:complete_json).and_return(reader_result(
        status: "overdue",
        events: [
          {
            "type" => "promise",
            "message_id" => "m-friday",
            "sender" => "client",
            "quote" => "We have scheduled this and will pay this Friday.",
            "data" => { "relative_phrase" => "this Friday", "anchor_date" => "2026-09-19" }
          },
          {
            "type" => "dispute",
            "message_id" => "m-dispute",
            "sender" => "client",
            "quote" => "We only owe $800.",
            "data" => { "amount" => 800 }
          },
          {
            "type" => "amount_correction",
            "message_id" => "m-accept",
            "sender" => "user",
            "quote" => "Confirmed, $800 it is. I have applied a $200 credit memo to reflect our agreement.",
            "data" => { "amount" => 800 }
          }
        ]
      ))

      result = described_class.execute(invoice: invoice, client: llm)

      expect(result).to be_success
      expect(invoice.reload.current_ar_status).to eq("promised")
      expect(invoice.active_promise_date).to eq(Date.new(2026, 9, 25))
      expect(invoice.disputed_claim_amount).to be_nil
      expect(invoice.needs_reply).to eq(false)
      expect(invoice.invoice_state_transitions.last.to_status).to eq("promised")
    end
  end

  it "recovers a standing Friday from the thread when the reader omits the promise event" do
    travel_to Time.utc(2026, 9, 19, 12) do
      invoice.update!(due_date: Date.new(2026, 9, 14), current_ar_status: "overdue", total_amount: 1000, balance_remaining: 1000)
      add_message!(
        id: "m-friday",
        from: "ap@acme.com",
        to: "owner@studio.com",
        direction: "client_to_user",
        body: "We have scheduled this and will pay this Friday.",
        sent_at: Time.utc(2026, 9, 19, 9, 48)
      )
      add_message!(
        id: "m-dispute",
        from: "ap@acme.com",
        to: "owner@studio.com",
        direction: "client_to_user",
        body: "Wait, stop the payment! We only owe $800.",
        sent_at: Time.utc(2026, 9, 19, 9, 49)
      )
      add_message!(
        id: "m-accept",
        from: "owner@studio.com",
        to: "ap@acme.com",
        direction: "user_to_client",
        body: "Confirmed, $800 it is. I have applied a $200 credit memo to reflect our agreement.",
        sent_at: Time.utc(2026, 9, 19, 9, 50)
      )
      allow(llm).to receive(:complete_json).and_return(reader_result(
        status: "overdue",
        events: [ {
          "type" => "amount_correction",
          "message_id" => "m-accept",
          "sender" => "user",
          "quote" => "Confirmed, $800 it is. I have applied a $200 credit memo to reflect our agreement.",
          "data" => { "amount" => 800 }
        } ]
      ))

      result = described_class.execute(invoice: invoice, client: llm)

      expect(result).to be_success
      expect(invoice.reload.current_ar_status).to eq("promised")
      expect(invoice.active_promise_date).to eq(Date.new(2026, 9, 25))
      expect(invoice.disputed_claim_amount).to be_nil
    end
  end

  it "clears needs_reply when a later user message answers the question" do
    add_message!(
      id: "m-q",
      from: "ap@acme.com",
      to: "owner@studio.com",
      direction: "client_to_user",
      body: "Can you confirm whether the wire for $500.00 hit your account?",
      sent_at: Time.utc(2026, 9, 16, 10),
      thread_id: "t-wire"
    )
    add_message!(
      id: "m-a",
      from: "owner@studio.com",
      to: "ap@acme.com",
      direction: "user_to_client",
      body: "Checked with HDFC Bank—no deposit has arrived yet.",
      sent_at: Time.utc(2026, 9, 16, 11),
      thread_id: "t-wire"
    )
    allow(llm).to receive(:complete_json).and_return(reader_result(
      status: "promised",
      needs_reply: true,
      events: [ {
        "type" => "promise",
        "message_id" => "m-q",
        "sender" => "client",
        "quote" => "Can you confirm whether the wire for $500.00 hit your account?"
      } ]
    ))

    result = described_class.execute(invoice: invoice, client: llm)

    expect(result).to be_success
    expect(invoice.reload.needs_reply).to eq(false)
    expect(invoice.current_ar_status).to eq("invoiced")
    expect(invoice.invoice_events.map(&:event_type)).to eq([ "needs_reply" ])
    expect(llm).to have_received(:complete_json) do |user:, **|
      payload = JSON.parse(user)
      expect(payload["messages"].map { |row| row["id"] }).to eq(%w[m-q m-a])
    end
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
