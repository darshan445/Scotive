# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::Enqueue do
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
      due_date: Date.new(2026, 9, 21),
      total_amount: 250,
      balance_remaining: 250,
      books_status: "open",
      pay_link_token: "https://pay.qbo.test/inv-12",
      cc_emails: [ "cfo@acme.com" ]
    )
  end

  def add_home_thread!
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation.messages.create!(
      external_message_id: "msg-1",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ "ap@acme.com" ],
      sent_at: Time.utc(2026, 9, 1, 12),
      clean_body: "Invoice attached",
      is_anchor: true,
      created_at: Time.current
    )
    conversation
  end

  it "schedules Friendly steps and drafts Firm/Final" do
    travel_to Time.utc(2026, 9, 18, 8) do
      add_home_thread!
      friendly = described_class.execute(invoice: invoice, step: "notice_minus_3")
      firm = described_class.execute(invoice: invoice, step: "firm_plus_7")

      expect(friendly.success?).to eq(true)
      expect(friendly.data[:created]).to eq(true)
      expect(friendly.data[:status]).to eq("scheduled")
      expect(firm.data[:status]).to eq("draft")

      row = invoice.outbox_messages.find_by!(cadence_step: "notice_minus_3")
      expect(row.to_address).to eq("ap@acme.com")
      expect(row.cc_addresses).to eq([ "cfo@acme.com" ])
      expect(row.subject).to eq("Re: INV-12")
      expect(row.body).to include("INV-12")
      expect(row.body).to include("Pay here: https://pay.qbo.test/inv-12")
      expect(row.scheduled_send_at).to eq(Time.utc(2026, 9, 18, 10, 15))
    end
  end

  it "schedules send at 10:15 in the organization timezone" do
    organization.update!(time_zone: "America/New_York")
    travel_to Time.utc(2026, 9, 18, 12) do
      add_home_thread!
      result = described_class.execute(invoice: invoice, step: "notice_minus_3")
      expect(result.data[:created]).to eq(true)
      row = invoice.outbox_messages.find_by!(cadence_step: "notice_minus_3")
      expect(row.scheduled_send_at).to eq(Time.utc(2026, 9, 18, 14, 15))
    end
  end

  it "drafts Friendly steps when auto-send is off" do
    organization.update!(friendly_auto_send: false)
    add_home_thread!
    result = described_class.execute(invoice: invoice, step: "due_today")
    expect(result.data[:status]).to eq("draft")
  end

  it "skips paid invoices, missing email, missing home thread, and duplicate pending steps" do
    add_home_thread!
    paid = described_class.execute(invoice: invoice.tap { |row| row.update!(books_status: "paid", balance_remaining: 0) }, step: "due_today")
    expect(paid.data[:created]).to eq(false)
    expect(paid.data[:reason]).to eq("terminal")

    invoice.update!(books_status: "open", balance_remaining: 250)
    first = described_class.execute(invoice: invoice, step: "due_today")
    dup = described_class.execute(invoice: invoice, step: "due_today")
    expect(first.data[:created]).to eq(true)
    expect(dup.data[:reason]).to eq("already_pending")

    invoice.client.update!(primary_email: nil)
    no_email = described_class.execute(invoice: invoice, step: "nudge_plus_3")
    expect(no_email.data[:reason]).to eq("no_email")
  end

  it "never enqueues the ladder after a human reply" do
    add_home_thread!
    invoice.update!(chase_status: "watching", last_human_inbound_at: Time.utc(2026, 9, 17, 12))
    result = described_class.execute(invoice: invoice, step: "due_today")
    expect(result.data[:created]).to eq(false)
    expect(result.data[:reason]).to eq("human_conversation")

    firm = described_class.execute(invoice: invoice, step: "firm_plus_7")
    expect(firm.data[:created]).to eq(false)
    expect(firm.data[:reason]).to eq("human_conversation")
  end

  it "skips when there is no Home Thread" do
    result = described_class.execute(invoice: invoice, step: "due_today")
    expect(result.data[:created]).to eq(false)
    expect(result.data[:reason]).to eq("no_home_thread")
  end
end
