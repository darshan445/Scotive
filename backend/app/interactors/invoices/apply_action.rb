# frozen_string_literal: true

# Invoices::ApplyAction Interactor
# Purpose: Resume / Wait until / Stop / mark paid from the ledger. No LLM.
# Methods:
# - execute

class Invoices::ApplyAction
  include ExecuteMethodHelper
  include LogHelper
  include Invoices::ChaseWrite

  ACTIONS = %w[resume wait_until stop_chasing mark_paid set_due_date skip_followup].freeze

  def self.execute(organization:, invoice_id:, action:, due_date: nil, wait_until: nil)
    new(
      organization: organization,
      invoice_id: invoice_id,
      action: action,
      due_date: due_date,
      wait_until: wait_until
    ).execute
  end

  def initialize(organization:, invoice_id:, action:, due_date:, wait_until:)
    @organization = organization
    @invoice_id = invoice_id
    @action = action.to_s
    @due_date = due_date
    @wait_until = wait_until
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?
      raise_string_error("Unknown action") unless ACTIONS.include?(action)

      invoice = nil
      Invoice.transaction do
        invoice = organization.invoices.lock.find_by(id: invoice_id)
        raise_string_error("Invoice not found") if invoice.blank?

        case action
        when "resume" then apply_resume_to_ladder!(invoice)
        when "wait_until" then wait_until!(invoice)
        when "stop_chasing" then apply_stop!(invoice)
        when "mark_paid" then mark_paid!(invoice)
        when "set_due_date" then set_due_date!(invoice)
        when "skip_followup" then skip_followup!(invoice)
        end
      end

      {
        action: action,
        status: invoice.list_bucket,
        chase_status: invoice.chase_status,
        books_status: invoice.books_status,
        invoice: Ledger::InvoicePayload.for(invoice.reload)
      }
    end
  end

  private

  attr_reader :organization, :invoice_id, :action, :due_date, :wait_until

  def wait_until!(invoice)
    parsed = parse_date(wait_until.presence || due_date)
    raise_string_error("Wait-until date is required") if parsed.blank?

    quote = invoice.outbox_messages.pending.order(created_at: :desc).first&.suggested_wait_quote
    apply_wait_until!(invoice, parsed, quote: quote)
  end

  def mark_paid!(invoice)
    invoice.balance_remaining = 0
    apply_books_status!(invoice, "paid")
  end

  def skip_followup!(invoice)
    invoice.outbox_messages.where(status: "draft").find_each do |row|
      row.update!(status: "cancelled", cancellation_reason: "skipped_by_user")
    end
  end

  def set_due_date!(invoice)
    parsed = parse_date(due_date)
    raise_string_error("Due date is required") if parsed.blank?

    invoice.update!(due_date: parsed)
  end

  def parse_date(value)
    return if value.blank?
    return value.to_date if value.respond_to?(:to_date) && !value.is_a?(String)

    Date.parse(value.to_s)
  rescue Date::Error, ArgumentError
    nil
  end
end
