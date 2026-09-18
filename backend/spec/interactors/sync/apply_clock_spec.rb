# frozen_string_literal: true

require "rails_helper"

RSpec.describe Sync::ApplyClock do
  include ActiveSupport::Testing::TimeHelpers

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

  def create_invoice!(status:, due_date:, promise_date: nil, balance: 100)
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: SecureRandom.hex(4),
      invoice_number: "INV-#{SecureRandom.hex(2)}",
      issue_date: Date.new(2026, 8, 1),
      due_date: due_date,
      total_amount: 100,
      balance_remaining: balance,
      current_ar_status: status,
      active_promise_date: promise_date
    )
  end

  it "moves past-due invoiced rows to overdue and expired promises to broken_promise" do
    travel_to Time.utc(2026, 9, 18, 12) do
      overdue_row = create_invoice!(status: "invoiced", due_date: Date.new(2026, 9, 17))
      still_open = create_invoice!(status: "invoiced", due_date: Date.new(2026, 9, 19))
      broken = create_invoice!(status: "promised", due_date: Date.new(2026, 9, 30), promise_date: Date.new(2026, 9, 17))
      waiting = create_invoice!(status: "promised", due_date: Date.new(2026, 9, 30), promise_date: Date.new(2026, 9, 20))
      paid = create_invoice!(status: "invoiced", due_date: Date.new(2026, 9, 1), balance: 0)

      result = described_class.execute(organization: organization)
      expect(result.success?).to eq(true)
      expect(result.data[:overdue]).to eq(1)
      expect(result.data[:broken_promise]).to eq(1)
      expect(overdue_row.reload.current_ar_status).to eq("overdue")
      expect(overdue_row.invoice_state_transitions.last.trigger_source).to eq("clock_cron")
      expect(still_open.reload.current_ar_status).to eq("invoiced")
      expect(broken.reload.current_ar_status).to eq("broken_promise")
      expect(waiting.reload.current_ar_status).to eq("promised")
      expect(paid.reload.current_ar_status).to eq("invoiced")
    end
  end

  it "enqueues a broken-promise draft when an expired promise flips" do
    travel_to Time.utc(2026, 9, 18, 12) do
      mailbox = organization.integrations.create!(
        category: "mailbox",
        provider: "gmail",
        external_account_id: "acc-gmail",
        account_name: "owner@studio.com",
        connection_status: "connected"
      )
      invoice = create_invoice!(status: "promised", due_date: Date.new(2026, 9, 30), promise_date: Date.new(2026, 9, 17))
      conversation = organization.conversations.create!(
        integration: mailbox,
        external_thread_id: "t-home",
        subject: invoice.invoice_number
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

      result = described_class.execute(organization: organization)
      expect(result.success?).to eq(true)
      row = invoice.outbox_messages.sole
      expect(invoice.reload.current_ar_status).to eq("broken_promise")
      expect(row.status).to eq("draft")
      expect(row.cadence_step).to eq("broken_promise")
    end
  end
end
