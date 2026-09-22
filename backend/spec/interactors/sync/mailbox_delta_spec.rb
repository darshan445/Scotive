# frozen_string_literal: true

require "rails_helper"

RSpec.describe Sync::MailboxDelta do
  include ActiveJob::TestHelper

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
      connection_status: "connected",
      last_synced_at: 1.day.ago
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
  let!(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-12",
      invoice_number: "INV-12",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 30),
      total_amount: 250,
      balance_remaining: 250,
      current_ar_status: "invoiced"
    )
  end
  let(:email_client) { instance_double(Email::EmailClient) }

  after { clear_enqueued_jobs }

  it "routes new mail since last_synced_at and skips already stored ids" do
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation.messages.create!(
      external_message_id: "old-1",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ "ap@acme.com" ],
      sent_at: 2.days.ago,
      clean_body: "Invoice attached",
      created_at: Time.current
    )

    allow(email_client).to receive(:list_emails).and_return(
      "items" => [
        {
          "id" => "old-1",
          "thread_id" => "t-home",
          "subject" => "INV-12",
          "body" => "Invoice attached",
          "date" => 2.days.ago.utc.iso8601,
          "from_attendee" => { "identifier" => "owner@studio.com" },
          "to_attendees" => [ { "identifier" => "ap@acme.com" } ]
        },
        {
          "id" => "new-2",
          "thread_id" => "t-home",
          "subject" => "INV-12",
          "body" => "Paying Friday",
          "date" => Time.utc(2026, 9, 18, 12).iso8601,
          "from_attendee" => { "identifier" => "ap@acme.com" },
          "to_attendees" => [ { "identifier" => "owner@studio.com" } ]
        }
      ]
    )

    result = described_class.execute(organization: organization, client: email_client)
    expect(result.success?).to eq(true)
    expect(result.data[:fetched]).to eq(2)
    expect(result.data[:persisted]).to eq(1)
    expect(result.data[:discarded]).to eq(1)
    expect(conversation.messages.find_by(external_message_id: "new-2")).to be_present
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(invoice.id)
    expect(mailbox.reload.last_synced_at).to be_within(5.seconds).of(Time.current)
  end

  it "uses the same as-of Pass 2 rules when send and unlabeled payment arrive in one window" do
    llm = instance_double(Email::LlmClient)
    allow(llm).to receive(:complete_json).and_return("intent" => "invoice_payment")
    allow(Email::LlmClient).to receive(:new).and_return(llm)
    later = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-99",
      invoice_number: "INV-99",
      issue_date: Date.new(2026, 9, 22),
      due_date: 10.days.from_now,
      total_amount: 99,
      balance_remaining: 99,
      current_ar_status: "invoiced"
    )
    allow(email_client).to receive(:list_emails).and_return(
      "items" => [
        {
          "id" => "m-pay",
          "thread_id" => "t-pay",
          "subject" => "Payment released",
          "body" => "We will pay the outstanding invoices this week.",
          "date" => Time.utc(2026, 9, 18, 14).iso8601,
          "from_attendee" => { "identifier" => "ap@acme.com" },
          "to_attendees" => [ { "identifier" => "owner@studio.com" } ]
        },
        {
          "id" => "m-send",
          "thread_id" => "t-send",
          "subject" => "Invoice INV-12",
          "body" => "Invoice INV-12 is attached.",
          "date" => Time.utc(2026, 9, 18, 12).iso8601,
          "from_attendee" => { "identifier" => "owner@studio.com" },
          "to_attendees" => [ { "identifier" => "ap@acme.com" } ]
        }
      ]
    )

    result = described_class.execute(organization: organization, client: email_client)
    expect(result.success?).to eq(true)
    expect(invoice.conversations.find_by(external_thread_id: "t-pay")).to be_present
    expect(later.conversations.find_by(external_thread_id: "t-pay")).to be_blank
    expect(home = invoice.conversations.find_by(external_thread_id: "t-send")).to be_present
    expect(invoice.invoice_conversations.find_by(conversation: home).is_primary?).to eq(true)
  end
end
