# frozen_string_literal: true

# Cadence::Schedule Interactor
# Purpose: morning pass — enqueue Friendly outbox rows for due milestones.
# Methods:
# - execute

class Cadence::Schedule
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

      created = 0
      skipped = 0
      Cadence::Steps.ladder_rows(organization).each do |config|
        counts = enqueue_due!(config)
        created += counts[:created]
        skipped += counts[:skipped]
      end
      { created: created, skipped: skipped }
    end
  end

  private

  attr_reader :organization

  def enqueue_due!(config)
    created = 0
    skipped = 0
    due_scope(config[:due_date]).find_each do |invoice|
      if record_created?(invoice, config[:key])
        created += 1
      else
        skipped += 1
      end
    end
    { created: created, skipped: skipped }
  end

  def due_scope(due_date)
    organization.invoices.books_open
      .where(chase_status: "watching", due_date: due_date, last_human_inbound_at: nil)
      .where("expected_pay_date IS NULL OR expected_pay_date >= ?", Date.current)
  end

  def record_created?(invoice, step)
    result = Cadence::Enqueue.execute(invoice: invoice, step: step)
    result.success? && result.data[:created]
  end
end
