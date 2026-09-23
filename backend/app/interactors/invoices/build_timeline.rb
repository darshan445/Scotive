# frozen_string_literal: true

# Invoices::BuildTimeline Interactor
# Purpose: Chronological chase events for the drawer timeline.
# Methods:
# - execute

class Invoices::BuildTimeline
  include ExecuteMethodHelper
  include LogHelper

  EVENT_KINDS = {
    "human_inbound" => "replied",
    "auto_reply_ignored" => "auto_reply",
    "bounce_ignored" => "bounce",
    "wait_set" => "waiting_until",
    "wait_expired" => "wait_date_passed",
    "resumed" => "resumed",
    "stopped" => "stopped",
    "books_paid" => "receipt",
    "books_voided" => "written_off",
    "books_partial" => "partial_payment",
    "friendly_sent" => "friendly_sent",
    "draft_sent" => "draft_sent"
  }.freeze

  def self.execute(organization:, invoice_id:)
    new(organization: organization, invoice_id: invoice_id).execute
  end

  def initialize(organization:, invoice_id:)
    @organization = organization
    @invoice_id = invoice_id
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      invoice = organization.invoices.includes(
        :client,
        :invoice_chase_events,
        invoice_conversations: :conversation
      ).find_by(id: invoice_id)
      raise_string_error("Invoice not found") if invoice.blank?

      {
        invoice: Ledger::InvoicePayload.for(invoice),
        events: events_for(invoice)
      }
    end
  end

  private

  attr_reader :organization, :invoice_id

  def events_for(invoice)
    thread_id = Ledger::InvoicePayload.primary_conversation(invoice)&.external_thread_id
    rows = [
      {
        kind: "invoice_sent",
        date: invoice.issue_date&.to_time&.iso8601 || invoice.created_at.iso8601,
        amount: invoice.total_amount.to_f,
        due_date: invoice.due_date&.iso8601,
        thread_id: thread_id
      }
    ]
    invoice.invoice_chase_events.sort_by(&:created_at).each do |event|
      rows << {
        kind: EVENT_KINDS.fetch(event.event_type, event.event_type),
        date: event.created_at.iso8601,
        quote: event.quote,
        expected_pay_date: event.expected_pay_date&.iso8601,
        thread_id: thread_id,
        message_id: event.message_id
      }
    end
    rows.sort_by { |row| row[:date].to_s }
  end
end
