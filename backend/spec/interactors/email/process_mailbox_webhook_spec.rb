# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::ProcessMailboxWebhook do
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
      books_status: "open"
    )
  end
  let(:email_client) { instance_double(Email::EmailClient) }

  def event_for(payload)
    WebhookEvent.create!(
      organization: organization,
      integration: mailbox,
      provider: "gmail",
      external_event_id: "unipile:acc-gmail:mail_received:#{payload['email_id']}",
      payload: payload,
      status: "pending",
      created_at: Time.current
    )
  end

  after { clear_enqueued_jobs }

  it "persists onto a known thread and enqueues state eval" do
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    payload = {
      "event" => "mail_received",
      "account_id" => "acc-gmail",
      "email_id" => "m-2",
      "thread_id" => "t-home",
      "is_complete" => true,
      "subject" => "INV-12",
      "body" => "Paying Friday",
      "date" => Time.utc(2026, 9, 18, 12).iso8601,
      "from_attendee" => { "identifier" => "ap@acme.com" },
      "to_attendees" => [ { "identifier" => "owner@studio.com" } ]
    }

    result = nil
    expect {
      result = described_class.execute(webhook_event: event_for(payload), client: email_client)
    }.to have_enqueued_job(Email::EvaluateInvoiceStateJob).with(invoice.id)

    expect(result.success?).to eq(true)
    expect(conversation.messages.find_by(external_message_id: "m-2").direction).to eq("client_to_user")
  end

  it "matches an unknown thread by invoice number and registers the sender" do
    payload = {
      "event" => "mail_received",
      "account_id" => "acc-gmail",
      "email_id" => "m-new",
      "thread_id" => "t-new",
      "is_complete" => true,
      "subject" => "Re: INV-12",
      "body" => "About INV-12",
      "date" => Time.utc(2026, 9, 18, 13).iso8601,
      "from_attendee" => { "identifier" => "cpa@books.com" },
      "to_attendees" => [ { "identifier" => "owner@studio.com" } ]
    }

    result = described_class.execute(webhook_event: event_for(payload), client: email_client)
    expect(result.success?).to eq(true)
    expect(result.data[:routed]).to eq("unknown_match")
    expect(client_row.reload.associated_emails).to include("cpa@books.com")
    expect(invoice.conversations.find_by(external_thread_id: "t-new")).to be_present
  end

  it "discards mail that does not match an open invoice" do
    payload = {
      "event" => "mail_received",
      "account_id" => "acc-gmail",
      "email_id" => "m-spam",
      "thread_id" => "t-spam",
      "is_complete" => true,
      "subject" => "Hello",
      "body" => "Newsletter",
      "date" => Time.utc(2026, 9, 18, 14).iso8601,
      "from_attendee" => { "identifier" => "news@list.com" },
      "to_attendees" => [ { "identifier" => "owner@studio.com" } ]
    }

    result = described_class.execute(webhook_event: event_for(payload), client: email_client)
    expect(result.success?).to eq(true)
    expect(result.data[:discarded]).to eq(true)
    expect(organization.conversations.where(external_thread_id: "t-spam")).to be_empty
  end
end
