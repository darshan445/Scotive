# frozen_string_literal: true

# Cadence::Dispatch Interactor
# Purpose: five pre-flight guards, send Friendly on the Home Thread, persist the outbound message.
# Methods:
# - execute

class Cadence::Dispatch
  include ExecuteMethodHelper
  include LogHelper
  include Cadence::HomeThreadSend

  def self.execute(outbox_message:, client: Email::EmailClient.new)
    new(outbox_message: outbox_message, client: client).execute
  end

  def initialize(outbox_message:, client:)
    @outbox_message = outbox_message
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Outbox message is required") if outbox_message.blank?

      outcome = nil
      Invoice.transaction do
        invoice = organization.invoices.lock.find(outbox_message.invoice_id)
        row = organization.outbox_messages.lock.find(outbox_message.id)
        outcome = if row.status != "scheduled"
          { skipped: true, reason: "not_scheduled" }
        else
          reason = guard_reason(invoice)
          if reason
            cancel!(row, reason)
            { cancelled: true, reason: reason }
          else
            deliver_home_thread!(
              invoice: invoice,
              to: row.to_address,
              cc: Array(row.cc_addresses),
              subject: row.subject,
              body: row.body,
              client: client,
              outbox: row
            )
          end
        end
      end
      outcome
    end
  end

  private

  attr_reader :outbox_message, :client

  def organization
    outbox_message.organization
  end

  def guard_reason(invoice)
    if invoice.balance_remaining.to_d <= 0 || %w[paid voided].include?(invoice.current_ar_status)
      "paid_in_books"
    elsif invoice.needs_reply
      "client_awaiting_human_reply"
    elsif %w[disputed paid_unconfirmed promised].include?(invoice.current_ar_status)
      "blocked_by_status"
    elsif invoice.snoozed_until.present? && invoice.snoozed_until > Time.current
      "invoice_snoozed_by_user"
    elsif fatigue?(invoice)
      "anti_fatigue_cooldown"
    end
  end

  def fatigue?(invoice)
    since = 48.hours.ago
    client_invoice_ids = organization.invoices.where(client_id: invoice.client_id).select(:id)
    sent = OutboxMessage.where(invoice_id: client_invoice_ids, status: "sent")
      .where("sent_at > ?", since)
      .where.not(id: outbox_message.id)
    return true if sent.exists?

    Message.joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: client_invoice_ids })
      .where(direction: "user_to_client")
      .where("messages.sent_at > ?", since)
      .exists?
  end

  def cancel!(row, reason)
    row.update!(status: "cancelled", cancellation_reason: reason)
  end
end
