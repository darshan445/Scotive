# frozen_string_literal: true

require "rails_helper"

RSpec.describe Email::RouteInboundMessage do
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
  let!(:invoice) do
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "SIM-2301",
      invoice_number: "SIM-2301",
      issue_date: 20.days.ago.to_date,
      due_date: 5.days.from_now,
      total_amount: 230,
      balance_remaining: 230,
      current_ar_status: "invoiced"
    )
  end

  def message(id:, thread_id:, from:, to:, subject:, body:, cc: [])
    {
      id: id,
      thread_id: thread_id,
      subject: subject,
      from: from,
      to: Array(to),
      cc: Array(cc),
      sent_at: Time.current,
      raw_body: body,
      clean_body: body,
      attachment_names: []
    }
  end

  def route(msg, context_messages: nil)
    described_class.execute(
      organization: organization,
      mailbox: mailbox,
      message: msg,
      llm: llm,
      context_messages: context_messages
    )
  end

  it "discards an unlabeled Out of Office subject" do
    result = route(
      message(
        id: "m-ooo",
        thread_id: "t-ooo",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Automatic reply: I am out of the office",
        body: "Back next week."
      )
    )

    expect(result).to be_success
    expect(result.data[:discarded]).to eq(true)
    expect(result.data[:reason]).to eq("automatic_reply")
    expect(invoice.conversations.find_by(external_thread_id: "t-ooo")).to be_blank
  end

  it "discards unlabeled other_payment talk" do
    allow(llm).to receive(:complete_json).and_return("intent" => "other_payment")

    result = route(
      message(
        id: "m-quote",
        thread_id: "t-quote",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Quote for the spring add-on",
        body: "Need a new estimate. Budget is $4,000 for next quarter."
      )
    )

    expect(result).to be_success
    expect(result.data[:discarded]).to eq(true)
    expect(invoice.conversations.find_by(external_thread_id: "t-quote")).to be_blank
  end

  def persist_send!(invoice, sent_at: 5.days.ago)
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-send-#{invoice.invoice_number}",
      subject: "Invoice #{invoice.invoice_number}"
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation.messages.create!(
      external_message_id: "m-send-#{invoice.invoice_number}",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ invoice.client.primary_email ],
      sent_at: sent_at,
      clean_body: "Invoice #{invoice.invoice_number} is attached.",
      created_at: Time.current
    )
  end

  it "joint-links unlabeled invoice_payment to the only open invoice" do
    allow(llm).to receive(:complete_json).and_return("intent" => "invoice_payment")
    persist_send!(invoice)

    result = route(
      message(
        id: "m-pay",
        thread_id: "t-pay",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Payment released",
        body: "We will pay this week. Please confirm banking details."
      )
    )

    expect(result).to be_success
    expect(result.data[:routed]).to eq("unknown_match")
    expect(invoice.conversations.find_by(external_thread_id: "t-pay")).to be_present
    expect(Email::EvaluateInvoiceStateJob).to have_been_enqueued.with(invoice.id)
  end

  it "joint-links unlabeled payment when the send is only in the same mailbox window" do
    allow(llm).to receive(:complete_json).and_return("intent" => "invoice_payment")
    send = message(
      id: "m-send-window",
      thread_id: "t-send-window",
      from: "owner@studio.com",
      to: "ap@acme.com",
      subject: "Invoice SIM-2301",
      body: "Invoice SIM-2301 is attached."
    )
    send[:sent_at] = 1.hour.ago
    pay = message(
      id: "m-pay-window",
      thread_id: "t-pay-window",
      from: "ap@acme.com",
      to: "owner@studio.com",
      subject: "Payment released",
      body: "We will pay the outstanding invoices this week."
    )

    result = route(pay, context_messages: [ send, pay ])

    expect(result).to be_success
    expect(result.data[:routed]).to eq("unknown_match")
    expect(invoice.conversations.find_by(external_thread_id: "t-pay-window")).to be_present
  end

  it "does not joint-link unlabeled invoice_payment to a never-sent invoice" do
    allow(llm).to receive(:complete_json).and_return("intent" => "invoice_payment")

    result = route(
      message(
        id: "m-pay-miss",
        thread_id: "t-pay-miss",
        from: "ap@acme.com",
        to: "owner@studio.com",
        subject: "Payment released",
        body: "We will pay this week. Please confirm banking details."
      )
    )

    expect(result).to be_success
    expect(result.data[:discarded]).to eq(true)
    expect(invoice.conversations.find_by(external_thread_id: "t-pay-miss")).to be_blank
  end

  it "matches a CC'd AP alias and remembers the sender" do
    invoice.update!(cc_emails: [ "cpa@books.com" ])

    result = route(
      message(
        id: "m-cc",
        thread_id: "t-cc",
        from: "cpa@books.com",
        to: "owner@studio.com",
        subject: "SIM-2301",
        body: "Books has SIM-2301 in the pay run.",
        cc: [ "ap@acme.com" ]
      )
    )

    expect(result).to be_success
    expect(result.data[:routed]).to eq("unknown_match")
    expect(invoice.conversations.find_by(external_thread_id: "t-cc")).to be_present
    expect(client_row.reload.associated_emails).to include("cpa@books.com")
  end

  it "matches an unknown sender who quotes a pay-link identity" do
    url = "https://connect.intuit.com/portal/app/CommerceNetwork?jobId=f6a7b8c9-d0e1-4234-fa67-8901234567ab"
    invoice.update!(pay_link_token: url)

    result = route(
      message(
        id: "m-cpa-link",
        thread_id: "t-cpa-link",
        from: "cpa@outside.com",
        to: "owner@studio.com",
        subject: "Pay page",
        body: "Paying via #{url}"
      )
    )

    expect(result).to be_success
    expect(result.data[:routed]).to eq("unknown_match")
    expect(invoice.conversations.find_by(external_thread_id: "t-cpa-link")).to be_present
    expect(client_row.reload.associated_emails).to include("cpa@outside.com")
  end
end
