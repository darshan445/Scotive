# frozen_string_literal: true

# Settings payload shared by show + update.
module Settings::Serialize
  module_function

  def payload(organization)
    {
      time_zone: organization.time_zone,
      daily_digest_timezone: organization.time_zone,
      daily_digest_enabled: organization.daily_digest_enabled,
      daily_digest_hour: organization.daily_digest_hour,
      last_digest_sent_at: organization.last_digest_sent_at&.iso8601,
      friendly_auto_send: organization.friendly_auto_send,
      friendly_reminders: organization.friendly_reminders,
      escalation_offsets: organization.ladder_offsets
    }
  end
end
