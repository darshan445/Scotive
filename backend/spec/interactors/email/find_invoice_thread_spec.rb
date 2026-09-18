# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::FindInvoiceThread do
  include ActiveJob::TestHelper

  after { clear_enqueued_jobs }

  let(:organization) { Organization.create!(name: "Ada's workspace") }
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      access_token: "at",
      connection_status: "connected",
      last_synced_at: 1.hour.ago
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
  let(:email_client) { instance_double(Email::EmailClient) }
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
      external_id: "INV-404",
      invoice_number: "INV-404",
      issue_date: 20.days.ago.to_date,
      due_date: 5.days.from_now,
      total_amount: 404.00,
      balance_remaining: 404.00,
      pay_link_token: "tok-404",
      current_ar_status: "invoiced"
    )
  end

  def mail(id:, thread_id:, from:, to:, subject:, body:, date: 2.days.ago.utc.iso8601)
    {
      "id" => id,
      "thread_id" => thread_id,
      "subject" => subject,
      "body" => body,
      "body_plain" => body,
      "date" => date,
      "from_attendee" => { "identifier" => from },
      "to_attendees" => [ { "identifier" => to } ],
      "cc_attendees" => []
    }
  end

  def stub_searches
    allow(email_client).to receive(:list_emails) do |**kwargs|
      yield(kwargs)
    end
  end

  def execute
    described_class.execute(invoice: invoice, client: email_client)
  end

  it "matches Query A by pay-link token from an unknown CPA and stores the sender" do
    stub_searches do |kwargs|
      if kwargs[:search].to_s.include?("tok-404")
        { "items" => [
          mail(
            id: "m-cpa",
            thread_id: "t-cpa",
            from: "cpa@books.com",
            to: "owner@studio.com",
            subject: "Payment",
            body: "Pay with tok-404"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("A")
    expect(invoice.conversations.find_by!(external_thread_id: "t-cpa").invoice_conversations.first).to be_is_primary
    expect(client_row.reload.associated_emails).to include("cpa@books.com")
    expect(email_client).not_to have_received(:list_emails).with(hash_including(search: a_string_including("INV-404")))
  end

  it "falls through to Query B on client contacts + invoice number" do
    invoice.update!(pay_link_token: nil)
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("INV-404") && search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-number",
            thread_id: "t-number",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "Re: INV-404",
            body: "Got it"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("B")
    expect(invoice.conversations.find_by(external_thread_id: "t-number")).to be_present
    expect(Message.last.direction).to eq("client_to_user")
    expect(invoice.reload.current_ar_status).to eq("invoiced")
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(invoice.id)
  end

  it "falls through to Query C on sent mail from:me" do
    invoice.update!(pay_link_token: nil)
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [
          mail(
            id: "m-sent",
            thread_id: "t-sent",
            from: "owner@studio.com",
            to: "other@cpa.com",
            subject: "INV-404",
            body: "Invoice attached"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("C")
    expect(invoice.conversations.find_by(external_thread_id: "t-sent")).to be_present
    expect(invoice.reload.current_ar_status).to eq("invoiced")
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end

  it "falls through to Query D on contacts + total amount" do
    invoice.update!(pay_link_token: nil, invoice_number: "NOMATCH")
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("404.00") && search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-amt",
            thread_id: "t-amt",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "Balance",
            body: "We still have $404.00 open"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("D")
    expect(invoice.conversations.find_by(external_thread_id: "t-amt")).to be_present
  end

  it "marks the invoice unmatched when A→E are exhausted" do
    stub_searches { { "items" => [] } }

    result = execute

    expect(result).to be_success
    expect(result.data[:matched]).to eq(false)
    expect(result.data[:unmatched]).to eq(true)
    expect(invoice.reload.current_ar_status).to eq("unmatched")
    expect(invoice.invoice_state_transitions.last.trigger_source).to eq("mailbox_match")
    expect(invoice.conversations).to be_empty
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end

  it "links extra threads as split and clocks outbound-only overdue mail" do
    invoice.update!(due_date: 3.days.ago)
    stub_searches do |kwargs|
      if kwargs[:search].to_s.include?("tok-404")
        { "items" => [
          mail(
            id: "m-home",
            thread_id: "t-home",
            from: "owner@studio.com",
            to: "cpa@books.com",
            subject: "Invoice",
            body: "tok-404"
          ),
          mail(
            id: "m-split",
            thread_id: "t-split",
            from: "owner@studio.com",
            to: "cpa@books.com",
            subject: "Fwd",
            body: "tok-404 copy"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    links = invoice.invoice_conversations.includes(:conversation).order(:created_at)
    expect(links.map { |row| [ row.conversation.external_thread_id, row.is_primary ] }).to contain_exactly(
      [ "t-home", true ],
      [ "t-split", false ]
    )
    expect(invoice.reload.current_ar_status).to eq("overdue")
  end

  it "skips search when a thread is already linked" do
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-existing",
      subject: "Already matched"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    allow(email_client).to receive(:list_emails)

    result = execute

    expect(result).to be_success
    expect(result.data[:matched]).to eq(true)
    expect(email_client).not_to have_received(:list_emails)
  end

  it "uses Outlook from + after for Query C and does not combine search with after" do
    mailbox.update!(provider: "outlook")
    invoice.update!(pay_link_token: nil)
    stub_searches do |kwargs|
      if kwargs[:from] == "owner@studio.com"
        { "items" => [
          mail(
            id: "m-ol",
            thread_id: "t-ol",
            from: "owner@studio.com",
            to: "other@cpa.com",
            subject: "INV-404",
            body: "sent copy"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("C")
    expect(email_client).to have_received(:list_emails).with(
      hash_including(search: "INV-404", after: nil)
    )
    expect(email_client).to have_received(:list_emails).with(
      hash_including(from: "owner@studio.com", after: a_string_matching(/T/))
    )
  end
end
