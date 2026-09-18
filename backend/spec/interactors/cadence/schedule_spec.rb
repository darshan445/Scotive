# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::Schedule do
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

  def create_invoice!(status:, due_date:, number:, promise_date: nil)
    invoice = organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: number,
      invoice_number: number,
      issue_date: Date.new(2026, 8, 1),
      due_date: due_date,
      total_amount: 100,
      balance_remaining: 100,
      current_ar_status: status,
      active_promise_date: promise_date
    )
    conversation = organization.conversations.create!(
      integration: mailbox,
      external_thread_id: "t-#{number}",
      subject: number
    )
    InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
    conversation.messages.create!(
      external_message_id: "msg-#{number}",
      direction: "user_to_client",
      from_address: "owner@studio.com",
      to_addresses: [ "ap@acme.com" ],
      sent_at: Time.utc(2026, 8, 2, 12),
      clean_body: "Invoice attached",
      is_anchor: true,
      created_at: Time.current
    )
    invoice
  end

  it "creates Friendly scheduled rows and Firm/broken-promise drafts for today's milestones" do
    travel_to Time.utc(2026, 9, 18, 8) do
      notice = create_invoice!(status: "invoiced", due_date: Date.new(2026, 9, 21), number: "INV-N3")
      due = create_invoice!(status: "invoiced", due_date: Date.new(2026, 9, 18), number: "INV-D0")
      nudge = create_invoice!(status: "overdue", due_date: Date.new(2026, 9, 15), number: "INV-N3B")
      firm = create_invoice!(status: "overdue", due_date: Date.new(2026, 9, 11), number: "INV-F7")
      urgent = create_invoice!(status: "overdue", due_date: Date.new(2026, 9, 4), number: "INV-U14")
      broken = create_invoice!(status: "broken_promise", due_date: Date.new(2026, 9, 1), number: "INV-BP", promise_date: Date.new(2026, 9, 10))
      other = create_invoice!(status: "invoiced", due_date: Date.new(2026, 9, 30), number: "INV-SKIP")

      result = described_class.execute(organization: organization)
      expect(result.success?).to eq(true)
      expect(result.data[:created]).to eq(6)

      expect(notice.outbox_messages.sole.status).to eq("scheduled")
      expect(notice.outbox_messages.sole.cadence_step).to eq("notice_minus_3")
      expect(due.outbox_messages.sole.cadence_step).to eq("due_today")
      expect(nudge.outbox_messages.sole.cadence_step).to eq("nudge_plus_3")
      expect(firm.outbox_messages.sole).to have_attributes(status: "draft", cadence_step: "firm_plus_7")
      expect(urgent.outbox_messages.sole).to have_attributes(status: "draft", cadence_step: "urgent_plus_14")
      expect(broken.outbox_messages.sole).to have_attributes(status: "draft", cadence_step: "broken_promise")
      expect(other.outbox_messages).to be_empty
    end
  end
end
