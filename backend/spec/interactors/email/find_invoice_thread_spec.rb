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
  let(:llm) { instance_double(Email::LlmClient) }
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
      books_status: "open"
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
    described_class.execute(invoice: invoice, client: email_client, llm: llm)
  end

  it "matches the outbound home thread from:me + invoice number" do
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
    expect(result.data[:query]).to eq("home")
    expect(invoice.conversations.find_by(external_thread_id: "t-sent")).to be_present
    expect(invoice.conversations.find_by!(external_thread_id: "t-sent").invoice_conversations.first).to be_is_primary
    expect(invoice.reload.books_status).to eq("open")
    expect(invoice.chase_status).to eq("watching")
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end

  it "keeps the oldest from:me send as HOME when a later owner reply also matches the search" do
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [
          mail(
            id: "m-reply",
            thread_id: "t-remit",
            from: "owner@studio.com",
            to: "ap@acme.com",
            subject: "Re: Remittance INV-404",
            body: "Thanks, watching INV-404.",
            date: 1.day.ago.utc.iso8601
          ),
          mail(
            id: "m-send",
            thread_id: "t-sent",
            from: "owner@studio.com",
            to: "ap@acme.com",
            subject: "INV-404",
            body: "Invoice attached",
            date: 5.days.ago.utc.iso8601
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("home")
    home = invoice.invoice_conversations.includes(:conversation).find_by!(is_primary: true)
    expect(home.conversation.external_thread_id).to eq("t-sent")
    expect(invoice.conversations.find_by(external_thread_id: "t-remit")).to be_present
    expect(invoice.invoice_conversations.find_by(conversation: invoice.conversations.find_by!(external_thread_id: "t-remit"))).not_to be_is_primary
  end

  it "clusters client mail by invoice number when outbound home is missing" do
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [] }
      elsif search.include?("from:ap@acme.com")
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
    expect(result.data[:query]).to eq("client")
    expect(invoice.conversations.find_by(external_thread_id: "t-number")).to be_present
    expect(Message.last.direction).to eq("client_to_user")
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(invoice.id)
  end

  it "joint-links an unlabeled payment orphan to every open invoice" do
    sibling = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-405",
      invoice_number: "INV-405",
      issue_date: 20.days.ago.to_date,
      due_date: 5.days.from_now,
      total_amount: 405.00,
      balance_remaining: 405.00,
      books_status: "open"
    )
    allow(llm).to receive(:complete_json).and_return("intent" => "invoice_payment")
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [] }
      elsif search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-send-404",
            thread_id: "t-send-404",
            from: "owner@studio.com",
            to: "ap@acme.com",
            subject: "Invoice INV-404",
            body: "Invoice INV-404 is attached.",
            date: 5.days.ago.utc.iso8601
          ),
          mail(
            id: "m-send-405",
            thread_id: "t-send-405",
            from: "owner@studio.com",
            to: "ap@acme.com",
            subject: "Invoice INV-405",
            body: "Invoice INV-405 is attached.",
            date: 5.days.ago.utc.iso8601
          ),
          mail(
            id: "m-both",
            thread_id: "t-orphan",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "Payment released",
            body: "We will pay both outstanding invoices."
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("client")
    expect(invoice.conversations.find_by(external_thread_id: "t-orphan")).to be_present
    expect(sibling.conversations.find_by(external_thread_id: "t-orphan")).to be_present
  end

  it "links a sibling invoice numbered on the same client thread" do
    sibling = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-405",
      invoice_number: "INV-405",
      issue_date: 20.days.ago.to_date,
      due_date: 5.days.from_now,
      total_amount: 405.00,
      balance_remaining: 405.00,
      books_status: "open"
    )
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [] }
      elsif search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-shared",
            thread_id: "t-shared",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "Re: Invoice from Studio",
            body: "See INV-404 and INV-405"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-shared")).to be_present
    expect(sibling.conversations.find_by(external_thread_id: "t-shared")).to be_present
  end

  it "keeps clock status when search is exhausted" do
    invoice.update!(due_date: 3.days.ago, books_status: "open")
    stub_searches { { "items" => [] } }

    result = execute

    expect(result).to be_success
    expect(result.data[:matched]).to eq(false)
    expect(result.data[:unmatched]).to eq(true)
    expect(invoice.reload.books_status).to eq("open")
    expect(invoice.chase_status).to eq("watching")
    expect(invoice.conversations).to be_empty
  end

  it "leaves chase watching when search is exhausted" do
    invoice.update!(due_date: 3.days.ago, books_status: "open")
    stub_searches { { "items" => [] } }

    result = execute

    expect(result).to be_success
    expect(invoice.reload.books_status).to eq("open")
    expect(invoice.chase_status).to eq("watching")
  end

  it "matches an invoice number only present in quoted reply text" do
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [] }
      elsif search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-quoted",
            thread_id: "t-quoted",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "Re: Invoice from Studio",
            body: "We only owe $400.\nOn Mon, QBO wrote:\nInvoice INV-404 for $404.00 is attached."
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(invoice.conversations.find_by(external_thread_id: "t-quoted")).to be_present
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

  it "skips search when the invoice is already paid" do
    invoice.update!(books_status: "paid", balance_remaining: 0)
    allow(email_client).to receive(:list_emails)

    result = execute

    expect(result).to be_success
    expect(result.data[:matched]).to eq(false)
    expect(email_client).not_to have_received(:list_emails)
  end

  it "matches trailing digits on a client thread when outbound home is missing" do
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [] }
      elsif search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-digits",
            thread_id: "t-digits",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "Checking 404",
            body: "AP asked about 404 — still open?"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("client")
    expect(invoice.conversations.find_by(external_thread_id: "t-digits")).to be_present
  end

  it "does not attach unlabeled other_payment talk in the client cluster" do
    allow(llm).to receive(:complete_json).and_return("intent" => "other_payment")
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me")
        { "items" => [] }
      elsif search.include?("from:ap@acme.com")
        { "items" => [
          mail(
            id: "m-quote",
            thread_id: "t-quote",
            from: "ap@acme.com",
            to: "owner@studio.com",
            subject: "New estimate",
            body: "Can you quote the spring add-on? Budget is $4,000."
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:matched]).to eq(false)
    expect(invoice.conversations.find_by(external_thread_id: "t-quote")).to be_blank
  end

  it "uses Outlook from + after for the outbound home search" do
    mailbox.update!(provider: "outlook")
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
    expect(result.data[:query]).to eq("home")
    expect(email_client).to have_received(:list_emails).with(
      hash_including(from: "owner@studio.com", after: a_string_matching(/T/))
    )
  end

  it "matches from:me pay-link identity when the send has no invoice number" do
    url = "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=d4e5f6a7-b8c9-4012-de45-f67890123456"
    invoice.update!(pay_link_token: url, invoice_number: "SIM-2201")
    stub_searches do |kwargs|
      search = kwargs[:search].to_s
      if search.include?("from:me") && search.include?("d4e5f6a7-b8c9-4012-de45-f67890123456")
        { "items" => [
          mail(
            id: "m-plain",
            thread_id: "t-plain",
            from: "owner@studio.com",
            to: "ap@acme.com",
            subject: "Your invoice is ready",
            body: "Pay here: #{url}"
          )
        ] }
      else
        { "items" => [] }
      end
    end

    result = execute

    expect(result).to be_success
    expect(result.data[:query]).to eq("home")
    expect(invoice.conversations.find_by(external_thread_id: "t-plain")).to be_present
    expect(invoice.conversations.find_by!(external_thread_id: "t-plain").invoice_conversations.first).to be_is_primary
    expect(Email::EvaluateInvoiceStateJob).not_to have_been_enqueued
  end
end
