# frozen_string_literal: true

# Cadence::Enqueue Interactor
# Purpose: one pending outbox row per invoice + cadence step (Friendly scheduled, Firm/Final draft).
# Methods:
# - execute

class Cadence::Enqueue
  include ExecuteMethodHelper
  include LogHelper

  FRIENDLY_STEPS = %w[notice_minus_3 due_today nudge_plus_3].freeze
  DRAFT_STEPS = %w[firm_plus_7 urgent_plus_14 broken_promise].freeze
  STEPS = (FRIENDLY_STEPS + DRAFT_STEPS).freeze

  def self.execute(invoice:, step:)
    new(invoice: invoice, step: step).execute
  end

  def initialize(invoice:, step:)
    @invoice = invoice
    @step = step.to_s
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invoice is required") if invoice.blank?
      raise_string_error("Unknown cadence step") unless STEPS.include?(step)

      reason = skip_reason
      if reason
        { created: false, reason: reason }
      else
        row = create_row!
        if row
          { created: true, outbox_id: row.id, status: row.status }
        else
          { created: false, reason: "already_pending" }
        end
      end
    end
  end

  private

  attr_reader :invoice, :step

  def skip_reason
    if %w[paid voided].include?(invoice.current_ar_status) || invoice.balance_remaining.to_d <= 0
      "terminal"
    elsif invoice.client&.primary_email.blank?
      "no_email"
    elsif home_thread.blank?
      "no_home_thread"
    elsif pending_exists?
      "already_pending"
    end
  end

  def pending_exists?
    invoice.outbox_messages.pending.where(cadence_step: step).exists?
  end

  def create_row!
    invoice.outbox_messages.create!(
      organization_id: invoice.organization_id,
      conversation: home_thread,
      status: draft? ? "draft" : "scheduled",
      cadence_step: step,
      to_address: invoice.client.primary_email,
      cc_addresses: Array(invoice.cc_emails),
      subject: Cadence::Copy.subject(invoice, home_thread),
      body: Cadence::Copy.body(invoice, step),
      scheduled_send_at: send_at
    )
  rescue ActiveRecord::RecordNotUnique
    nil
  end

  def draft?
    DRAFT_STEPS.include?(step)
  end

  def send_at
    if step == "broken_promise"
      Time.current
    else
      Time.current.utc.change(hour: 10, min: 15)
    end
  end

  def home_thread
    @home_thread ||= begin
      link = invoice.invoice_conversations.find_by(is_primary: true)
      link&.conversation
    end
  end
end
