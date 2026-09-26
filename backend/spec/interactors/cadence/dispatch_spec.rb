# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::Dispatch do
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
      associated_emails: [ "ap@acme.com" ]
    )
  end
  let(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-12",
      invoice_number: "INV-12",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 15),
      total_amount: 250,
      balance_remaining: 250,
      books_status: "open",
      chase_status: "needs_you"
    )
  end
  let(:conversation) do
    record = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: record, is_primary: true, created_at: Time.current)
    record.messages.create!(
      external_message_id: "msg-anchor",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ "ap@acme.com" ],
      sent_at: Time.utc(2026, 9, 1, 12),
      clean_body: "Invoice attached",
      is_anchor: true,
      created_at: Time.current
    )
    record
  end
  let(:email_client) { instance_double(Email::EmailClient) }

  before do
    allow(email_client).to receive(:list_emails).and_return({ "items" => [] })
    allow(email_client).to receive(:get_email) { |id, **| { "id" => id } }
  end

  def create_outbox!(status: "scheduled", step: "nudge_plus_3")
    invoice.update!(chase_status: "watching")
    invoice.outbox_messages.create!(
      organization: organization,
      conversation: conversation,
      status: status,
      cadence_step: step,
      to_address: "ap@acme.com",
      cc_addresses: [ "cfo@acme.com" ],
      subject: "Re: INV-12",
      body: "Just checking in on invoice INV-12",
      scheduled_send_at: Time.utc(2026, 9, 18, 10, 15)
    )
  end

  it "sends on the Home Thread, stores the outbound message, and clears needs_reply" do
    travel_to Time.utc(2026, 9, 18, 10, 20) do
      row = create_outbox!
      allow(email_client).to receive(:send_email).and_return("id" => "msg-sent")

      result = described_class.execute(outbox_message: row, client: email_client)
      expect(result.success?).to eq(true)
      expect(result.data[:sent]).to eq(true)
      expect(row.reload.status).to eq("sent")
      expect(row.sent_at).to be_present
      expect(invoice.reload.chase_status).to eq("watching")

      sent = conversation.messages.find_by!(external_message_id: "msg-sent")
      expect(sent.direction).to eq("user_to_client")
      expect(sent.clean_body).to include("INV-12")
      expect(email_client).to have_received(:send_email).with(
        hash_including(
          account_id: "acc-gmail",
          to: "ap@acme.com",
          cc: [ "cfo@acme.com" ],
          reply_to: "msg-anchor",
          custom_headers: [
            { name: "X-Auto-Response-Suppress", value: "All" }
          ]
        )
      )
    end
  end

  it "skips drafts and cancels on the five pre-flight guards" do
    travel_to Time.utc(2026, 9, 18, 10, 20) do
      draft = create_outbox!(status: "draft", step: "firm_plus_7")
      skipped = described_class.execute(outbox_message: draft, client: email_client)
      expect(skipped.data[:reason]).to eq("not_scheduled")

      paid = create_outbox!(step: "due_today")
      invoice.update!(books_status: "paid", balance_remaining: 0)
      cancelled = described_class.execute(outbox_message: paid, client: email_client)
      expect(cancelled.data[:cancelled]).to eq(true)
      expect(cancelled.data[:reason]).to eq("paid_in_books")
      expect(paid.reload.status).to eq("cancelled")

      invoice.update!(books_status: "open", balance_remaining: 250, chase_status: "needs_you")
      turn = create_outbox!(step: "notice_minus_3")
      invoice.update!(chase_status: "needs_you")
      expect(described_class.execute(outbox_message: turn, client: email_client).data[:reason]).to eq("chase_paused")

      invoice.update!(chase_status: "stopped")
      blocked = create_outbox!(step: "nudge_plus_3")
      invoice.update!(chase_status: "stopped")
      expect(described_class.execute(outbox_message: blocked, client: email_client).data[:reason]).to eq("stopped_by_user")

      invoice.update!(books_status: "open", chase_status: "watching", expected_pay_date: 2.days.from_now.to_date)
      snoozed = create_outbox!(step: "due_today")
      invoice.update!(expected_pay_date: 2.days.from_now.to_date)
      expect(described_class.execute(outbox_message: snoozed, client: email_client).data[:reason]).to eq("waiting_until_date")

      invoice.update!(expected_pay_date: nil)
      conversation.messages.create!(
        external_message_id: "msg-recent",
        direction: "user_to_client",
        from_address: "owner@studio.com",
        to_addresses: [ "ap@acme.com" ],
        sent_at: 1.hour.ago,
        clean_body: "Checking in",
        created_at: Time.current
      )
      fatigue = create_outbox!(step: "notice_minus_3")
      expect(described_class.execute(outbox_message: fatigue, client: email_client).data[:reason]).to eq("anti_fatigue_cooldown")
    end
  end
end
