# frozen_string_literal: true

# Cadence::Schedule Interactor
# Purpose: morning pass — enqueue Friendly/Firm/Final/broken-promise outbox rows for due milestones.
# Methods:
# - execute

class Cadence::Schedule
  include ExecuteMethodHelper
  include LogHelper

  DUE_STEPS = {
    "notice_minus_3" => { due_offset: 3, statuses: %w[invoiced overdue partially_paid] },
    "due_today" => { due_offset: 0, statuses: %w[invoiced overdue partially_paid] },
    "nudge_plus_3" => { due_offset: -3, statuses: %w[overdue partially_paid] },
    "firm_plus_7" => { due_offset: -7, statuses: %w[overdue partially_paid] },
    "urgent_plus_14" => { due_offset: -14, statuses: %w[overdue partially_paid] }
  }.freeze

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      created = 0
      skipped = 0
      DUE_STEPS.each do |step, config|
        counts = enqueue_due!(step, config)
        created += counts[:created]
        skipped += counts[:skipped]
      end
      broken = enqueue_broken_promises!
      created += broken[:created]
      skipped += broken[:skipped]
      { created: created, skipped: skipped }
    end
  end

  private

  attr_reader :organization

  def enqueue_due!(step, config)
    due_date = Date.current + config[:due_offset]
    created = 0
    skipped = 0
    due_scope(config[:statuses], due_date).find_each do |invoice|
      if record_created?(invoice, step)
        created += 1
      else
        skipped += 1
      end
    end
    { created: created, skipped: skipped }
  end

  def enqueue_broken_promises!
    created = 0
    skipped = 0
    organization.invoices
      .where(current_ar_status: "broken_promise")
      .where("balance_remaining > 0")
      .find_each do |invoice|
        if record_created?(invoice, "broken_promise")
          created += 1
        else
          skipped += 1
        end
      end
    { created: created, skipped: skipped }
  end

  def due_scope(statuses, due_date)
    organization.invoices
      .where(current_ar_status: statuses, due_date: due_date)
      .where("balance_remaining > 0")
  end

  def record_created?(invoice, step)
    result = Cadence::Enqueue.execute(invoice: invoice, step: step)
    result.success? && result.data[:created]
  end
end
