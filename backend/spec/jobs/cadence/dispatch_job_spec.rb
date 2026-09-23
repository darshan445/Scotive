# frozen_string_literal: true

require "rails_helper"

RSpec.describe Cadence::DispatchJob, type: :job do
  include ActiveSupport::Testing::TimeHelpers

  it "dispatches scheduled rows that are due and ignores drafts" do
    travel_to Time.utc(2026, 9, 18, 10, 20) do
      organization = Organization.create!(name: "Ada's workspace")
      qbo = organization.integrations.create!(
        category: "accounting",
        provider: "qbo",
        external_account_id: "realm-1",
        account_name: "Studio",
        connection_status: "connected"
      )
      client_row = organization.clients.create!(
        integration: qbo,
        external_id: "1",
        name: "Acme",
        primary_email: "ap@acme.com"
      )
      invoice = organization.invoices.create!(
        integration: qbo,
        client: client_row,
        external_id: "INV-12",
        invoice_number: "INV-12",
        issue_date: Date.new(2026, 8, 1),
        due_date: Date.new(2026, 9, 15),
        total_amount: 100,
        balance_remaining: 100,
        books_status: "open"
      )
      due = invoice.outbox_messages.create!(
        organization: organization,
        status: "scheduled",
        cadence_step: "nudge_plus_3",
        to_address: "ap@acme.com",
        subject: "Re: INV-12",
        body: "Checking in",
        scheduled_send_at: Time.utc(2026, 9, 18, 10, 15)
      )
      invoice.outbox_messages.create!(
        organization: organization,
        status: "draft",
        cadence_step: "firm_plus_7",
        to_address: "ap@acme.com",
        subject: "Re: INV-12",
        body: "Firm follow-up",
        scheduled_send_at: Time.utc(2026, 9, 18, 10, 15)
      )
      allow(Cadence::Dispatch).to receive(:execute).and_return(OpenStruct.new(success?: true, data: { sent: true }))

      described_class.perform_now
      expect(Cadence::Dispatch).to have_received(:execute).once
      expect(Cadence::Dispatch).to have_received(:execute).with(outbox_message: due)
    end
  end
end
