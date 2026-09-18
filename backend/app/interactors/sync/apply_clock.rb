# frozen_string_literal: true

# Sync::ApplyClock Interactor
# Purpose: invoiced→overdue and promised→broken_promise. No provider I/O.
# Methods:
# - execute

class Sync::ApplyClock
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      {
        overdue: transition_due!,
        broken_promise: transition_promises!
      }
    end
  end

  private

  attr_reader :organization

  def transition_due!
    count = 0
    due_scope.find_each do |invoice|
      Invoice.transaction do
        row = organization.invoices.lock.find(invoice.id)
        next unless row.current_ar_status == "invoiced"
        next unless row.balance_remaining.to_d.positive?
        next unless row.due_date < Date.current

        row.update!(current_ar_status: "overdue")
        row.invoice_state_transitions.create!(
          from_status: "invoiced",
          to_status: "overdue",
          trigger_source: "clock_cron",
          created_at: Time.current
        )
        count += 1
      end
    end
    count
  end

  def transition_promises!
    count = 0
    broken_ids = []
    promise_scope.find_each do |invoice|
      Invoice.transaction do
        row = organization.invoices.lock.find(invoice.id)
        next unless row.current_ar_status == "promised"
        next unless row.balance_remaining.to_d.positive?
        next if row.active_promise_date.blank? || row.active_promise_date >= Date.current

        row.update!(current_ar_status: "broken_promise")
        row.invoice_state_transitions.create!(
          from_status: "promised",
          to_status: "broken_promise",
          trigger_source: "clock_cron",
          promise_date: row.active_promise_date,
          created_at: Time.current
        )
        broken_ids << row.id
        count += 1
      end
    end
    enqueue_broken_promise_drafts!(broken_ids)
    count
  end

  def enqueue_broken_promise_drafts!(invoice_ids)
    return if invoice_ids.empty?

    Invoice.where(id: invoice_ids, organization_id: organization.id).find_each do |invoice|
      Cadence::Enqueue.execute(invoice: invoice, step: "broken_promise")
    end
  end

  def due_scope
    organization.invoices
      .where(current_ar_status: "invoiced")
      .where("due_date < ?", Date.current)
      .where("balance_remaining > 0")
  end

  def promise_scope
    organization.invoices
      .where(current_ar_status: "promised")
      .where("active_promise_date < ?", Date.current)
      .where("balance_remaining > 0")
  end
end
