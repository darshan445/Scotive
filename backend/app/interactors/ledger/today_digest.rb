# frozen_string_literal: true

# Ledger::TodayDigest Interactor
# Purpose: Home “Needs you today” groups from live invoice state (org timezone).
# Methods:
# - execute

class Ledger::TodayDigest
  include ExecuteMethodHelper
  include LogHelper

  OPEN_STATUSES = %w[
    unmatched invoiced overdue promised broken_promise disputed paid_unconfirmed partially_paid
  ].freeze

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      groups = empty_groups
      open_invoices.find_each do |invoice|
        payload = Ledger::InvoicePayload.for(invoice)
        bucket = bucket_for(invoice)
        groups[bucket] << payload if bucket
      end
      groups.merge(merge_prompts: [])
    end
  end

  private

  attr_reader :organization

  def empty_groups
    {
      due_overdue: [],
      broken_promises: [],
      confirm_prompts: [],
      stale_prompts: [],
      needs_reply: []
    }
  end

  def open_invoices
    organization.invoices
      .where(current_ar_status: OPEN_STATUSES)
      .where("balance_remaining > 0")
      .where("snoozed_until IS NULL OR snoozed_until <= ?", Time.current)
      .includes(:client, :invoice_state_transitions, invoice_conversations: :conversation)
  end

  def bucket_for(invoice)
    status = invoice.current_ar_status
    if status == "overdue" || (status == "partially_paid" && invoice.due_date < organization.today)
      :due_overdue
    elsif status == "broken_promise"
      :broken_promises
    elsif %w[paid_unconfirmed disputed].include?(status)
      :confirm_prompts
    elsif invoice.needs_reply
      :needs_reply
    end
  end
end
