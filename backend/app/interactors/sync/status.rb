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
        pending_followup_prompts: []
      }
    end
  end

  private

  attr_reader :organization

  def last_synced_at
    organization.integrations.connected.map(&:last_synced_at).compact.max
  end
end
