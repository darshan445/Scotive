# frozen_string_literal: true

# Cadence::Schedule Interactor
# Purpose: morning pass — enqueue Friendly/Firm/Final/broken-promise outbox rows for due milestones.
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
      broken = enqueue_broken_promises!
      created += broken[:created]
      skipped += broken[:skipped]
      follow = enqueue_post_firm_follow_ups!
      created += follow[:created]
      skipped += follow[:skipped]
      { created: created, skipped: skipped }
    end
  end

  private

  attr_reader :organization

  def enqueue_due!(config)
    created = 0
    skipped = 0
    due_scope(config[:statuses], config[:due_date]).find_each do |invoice|
      if record_created?(invoice, config[:key])
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

  def enqueue_post_firm_follow_ups!
    created = 0
    skipped = 0
    interval = organization.follow_up_interval_days
    organization.outbox_messages
      .where(status: "sent", cadence_step: Cadence::Steps::FIRM)
      .where.not(sent_at: nil)
      .includes(:invoice)
      .find_each do |row|
        invoice = row.invoice
        next if invoice.blank?
        next unless days_since_send(row.sent_at) >= interval
        next if skip_final?(invoice, row.sent_at)

        if record_created?(invoice, Cadence::Steps::FINAL)
          created += 1
        else
          skipped += 1
        end
      end
    { created: created, skipped: skipped }
  end

  def days_since_send(sent_at)
    (organization.today - sent_at.in_time_zone(organization.zone).to_date).to_i
  end

  def skip_final?(invoice, sent_at)
    %w[paid voided].include?(invoice.current_ar_status) ||
      invoice.balance_remaining.to_d <= 0 ||
      invoice.outbox_messages.pending.where(cadence_step: Cadence::Steps::FINAL).exists? ||
      invoice.outbox_messages.where(status: "sent", cadence_step: Cadence::Steps::FINAL).exists? ||
      client_replied_since?(invoice, sent_at)
  end

  def client_replied_since?(invoice, since)
    return false if since.blank?

    Message
      .joins(conversation: :invoice_conversations)
      .where(invoice_conversations: { invoice_id: invoice.id }, direction: "client_to_user")
      .where("messages.sent_at > ?", since)
      .exists?
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
