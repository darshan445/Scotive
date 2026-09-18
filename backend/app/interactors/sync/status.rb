# frozen_string_literal: true

# Sync::Status Interactor
# Purpose: Running flag + last sync stamp for the dashboard strip.
# Methods:
# - execute

class Sync::Status
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

      mailbox = organization.integrations.mailbox.connected.first
      {
        sync_running: Sync::State.running?(organization.id),
        last_synced_at: last_synced_at&.iso8601,
        last_detected_at: last_synced_at&.iso8601,
        watching_sent_mail: mailbox.present?,
        counts: Sync::State.last_counts(organization.id),
        unread_detections: [],
        pending_due_date_prompts: [],
        pending_followup_prompts: pending_followup_prompts
      }
    end
  end

  private

  attr_reader :organization

  STEP_LABELS = {
    "notice_minus_3" => "pre_due_nudge",
    "due_today" => "due_reminder",
    "nudge_plus_3" => "friendly_followup",
    "firm_plus_7" => "firm_followup",
    "urgent_plus_14" => "final_notice",
    "broken_promise" => "promise_broken"
  }.freeze

  def last_synced_at
    organization.integrations.connected.map(&:last_synced_at).compact.max
  end

  def pending_followup_prompts
    organization.outbox_messages.where(status: "draft").includes(invoice: [ :client, :invoice_state_transitions, { invoice_conversations: :conversation } ]).filter_map do |row|
      invoice = row.invoice
      next if invoice.blank?
      next if %w[paid voided].include?(invoice.current_ar_status)
      next if Ledger::InvoicePayload.paused?(invoice)

      payload = Ledger::InvoicePayload.for(invoice)
      {
        invoice_id: invoice.id,
        draft_id: row.id,
        step_label: STEP_LABELS[row.cadence_step] || row.cadence_step,
        amount: payload[:amount],
        currency: payload[:currency],
        counterparty_name: payload[:counterparty_name],
        counterparty_email: payload[:counterparty_email]
      }
    end
  end
end
