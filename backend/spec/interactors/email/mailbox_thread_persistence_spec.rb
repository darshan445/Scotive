# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::MailboxThreadPersistence do
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
      external_id: "1064",
      invoice_number: "1064",
      issue_date: Date.new(2026, 9, 12),
      due_date: Date.new(2026, 9, 25),
      total_amount: 3240,
      balance_remaining: 3240,
      current_ar_status: "invoiced"
    )
  end
  let(:helper) do
    Class.new do
      include Email::MailboxThreadPersistence
      attr_reader :organization

      def initialize(organization)
        @organization = organization
      end
    end.new(organization)
  end

  it "keys Unipile list and webhook copies on Gmail provider_id and keeps one row" do
    sent_at = Time.utc(2026, 9, 22, 6, 57, 43)
    webhook = helper.send(
      :normalize_message,
      "email_id" => "GdrFaK8zU_yokzYExXyqLA",
      "provider_id" => "1a0c7e7f9b9a7a1c",
      "thread_id" => "1a0c7e7f9b9a7a1c",
      "message_id" => "<abc@mail.gmail.com>",
      "subject" => "Invoice 1064",
      "date" => sent_at.iso8601,
      "from_attendee" => { "identifier" => "owner@studio.com" },
      "to_attendees" => [ { "identifier" => "ap@acme.com" } ],
      "body" => "Your invoice is attached."
    )
    listed = helper.send(
      :normalize_message,
      "id" => "GdrFaK8zU_yokzYExXyqLA",
      "provider_id" => "1a0c7e7f9b9a7a1c",
      "thread_id" => "1a0c7e7f9b9a7a1c",
      "subject" => "Invoice 1064",
      "date" => sent_at.iso8601,
      "from_attendee" => { "identifier" => "owner@studio.com" },
      "to_attendees" => [ { "identifier" => "ap@acme.com" } ],
      "body" => "Your invoice is attached."
    )

    helper.persist_thread!(mailbox, invoice, webhook[:thread_id], [ webhook ], primary: true)
    helper.persist_thread!(mailbox, invoice, listed[:thread_id], [ listed ], primary: true)

    conversation = organization.conversations.find_by!(external_thread_id: "1a0c7e7f9b9a7a1c")
    expect(conversation.messages.count).to eq(1)
    expect(conversation.messages.first.external_message_id).to eq("1a0c7e7f9b9a7a1c")
  end

  it "collapses an already-stored Unipile id twin of the same send" do
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "1a0c7e7f9b9a7a1c",
      subject: "Invoice 1064"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    sent_at = Time.utc(2026, 9, 22, 6, 57, 43)
    conversation.messages.create!(
      external_message_id: "GdrFaK8zU_yokzYExXyqLA",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ "ap@acme.com" ],
      sent_at: sent_at,
      clean_body: "Your invoice is attached.",
      created_at: Time.current
    )

    helper.persist_thread!(
      mailbox,
      invoice,
      "1a0c7e7f9b9a7a1c",
      [ {
        id: "1a0c7e7f9b9a7a1c",
        thread_id: "1a0c7e7f9b9a7a1c",
        subject: "Invoice 1064",
        from: "owner@studio.com",
        to: [ "ap@acme.com" ],
        cc: [],
        sent_at: sent_at,
        raw_body: "Your invoice is attached.",
        clean_body: "Your invoice is attached.",
        attachment_names: []
      } ],
      primary: true
    )

    expect(conversation.messages.count).to eq(1)
    expect(conversation.messages.first.external_message_id).to eq("GdrFaK8zU_yokzYExXyqLA")
  end
end
