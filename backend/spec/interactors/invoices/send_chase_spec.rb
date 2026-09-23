# frozen_string_literal: true

require "rails_helper"

RSpec.describe Invoices::SendChase do
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
      chase_status: "needs_you",
      cc_emails: [ "cfo@acme.com" ]
    )
  end
  let(:email_client) { instance_double(Email::EmailClient) }

  def add_home_thread!
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-home",
      subject: "INV-12"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation.messages.create!(
      external_message_id: "msg-anchor",
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

  it "sends on the Home Thread even when needs_reply is set, then clears the flag" do
    travel_to Time.utc(2026, 9, 18, 12) do
      conversation = add_home_thread!
      draft = invoice.outbox_messages.create!(
        organization: organization,
        conversation: conversation,
        status: "draft",
        cadence_step: "firm_plus_7",
        to_address: "ap@acme.com",
        subject: "Re: INV-12",
        body: "Old firm copy",
        scheduled_send_at: Time.current
      )
      invoice.outbox_messages.create!(
        organization: organization,
        conversation: conversation,
        status: "scheduled",
        cadence_step: "nudge_plus_3",
        to_address: "ap@acme.com",
        subject: "Re: INV-12",
        body: "Friendly",
        scheduled_send_at: Time.current
      )
      allow(email_client).to receive(:send_email).and_return("id" => "msg-sent")

      result = described_class.execute(
        organization: organization,
        invoice_id: invoice.id,
        subject: "Re: INV-12",
        body: "Edited firm follow-up",
        client: email_client
      )
      expect(result.success?).to eq(true)
      expect(invoice.reload.chase_status).to eq("watching")
      expect(invoice.expected_pay_date).to be_nil
      expect(draft.reload.status).to eq("sent")
      expect(draft.body).to eq("Edited firm follow-up")
      expect(invoice.outbox_messages.find_by(cadence_step: "nudge_plus_3").status).to eq("cancelled")
      expect(conversation.messages.find_by!(external_message_id: "msg-sent").direction).to eq("user_to_client")
    end
  end

  it "does not restart the ladder after a human reply" do
    travel_to Time.utc(2026, 9, 18, 12) do
      conversation = add_home_thread!
      inbound = conversation.messages.create!(
        external_message_id: "msg-reply",
        direction: "client_to_user",
        from_address: "ap@acme.com",
        to_addresses: [ "owner@studio.com" ],
        sent_at: Time.utc(2026, 9, 17, 15),
        clean_body: "Checking with accounting",
        created_at: Time.current
      )
      invoice.update!(
        chase_status: "needs_you",
        last_human_inbound_at: inbound.sent_at,
        last_human_inbound_message: inbound
      )
      allow(email_client).to receive(:send_email).and_return("id" => "msg-reply-sent")

      result = described_class.execute(
        organization: organization,
        invoice_id: invoice.id,
        subject: "Re: INV-12",
        body: "Any update from accounting?",
        client: email_client
      )

      expect(result.success?).to eq(true)
      expect(invoice.reload.chase_status).to eq("needs_you")
      expect(invoice.expected_pay_date).to be_nil
    end
  end

  it "sends a reply and sleeps until the follow-up date" do
    travel_to Time.utc(2026, 9, 18, 12) do
      conversation = add_home_thread!
      inbound = conversation.messages.create!(
        external_message_id: "msg-reply",
        direction: "client_to_user",
        from_address: "ap@acme.com",
        to_addresses: [ "owner@studio.com" ],
        sent_at: Time.utc(2026, 9, 17, 15),
        clean_body: "Checking with accounting",
        created_at: Time.current
      )
      invoice.update!(
        chase_status: "needs_you",
        last_human_inbound_at: inbound.sent_at,
        last_human_inbound_message: inbound
      )
      allow(email_client).to receive(:send_email).and_return("id" => "msg-reply-sent")

      result = described_class.execute(
        organization: organization,
        invoice_id: invoice.id,
        subject: "Re: INV-12",
        body: "Any update from accounting?",
        wait_until: "2026-09-23",
        client: email_client
      )

      expect(result.success?).to eq(true)
      expect(invoice.reload.chase_status).to eq("watching")
      expect(invoice.expected_pay_date).to eq(Date.new(2026, 9, 23))
    end
  end

  it "refuses to send when books show the invoice paid" do
    add_home_thread!
    invoice.update!(books_status: "paid", balance_remaining: 0)
    result = described_class.execute(
      organization: organization,
      invoice_id: invoice.id,
      subject: "Re: INV-12",
      body: "Thanks",
      client: email_client
    )
    expect(result.success?).to eq(false)
    expect(result.errors).to match(/paid/)
  end
end
