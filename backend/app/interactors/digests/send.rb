# frozen_string_literal: true

# Digests::Send Interactor
# Purpose: email the Needs-you-today digest at each org's saved hour/timezone.
# Methods:
# - execute

class Digests::Send
  include ExecuteMethodHelper
  include LogHelper

  GROUP_KEYS = %i[needs_you].freeze

  def self.execute
    new.execute
  end

  def execute
    execute_log_and_return_open_struct do
      sent = 0
      skipped = 0
      Organization.where(daily_digest_enabled: true).find_each do |organization|
        unless local_hour?(organization)
          skipped += 1
          next
        end
        if already_sent_today?(organization)
          skipped += 1
          next
        end

        groups = validate_result(Ledger::TodayDigest.execute(organization: organization)).data
        unless actionable?(groups)
          skipped += 1
          next
        end

        recipients = organization.users.where(role: %w[owner admin])
        if recipients.none?
          skipped += 1
          next
        end

        recipients.find_each do |user|
          DigestMailer.daily(user: user, groups: groups).deliver_now
        end
        organization.update!(last_digest_sent_at: Time.current)
        sent += 1
      end
      { sent: sent, skipped: skipped }
    end
  end

  private

  def local_hour?(organization)
    now = Time.current.in_time_zone(organization.zone)
    now.hour == organization.daily_digest_hour && now.min < 15
  end

  def already_sent_today?(organization)
    last = organization.last_digest_sent_at
    last.present? && last.in_time_zone(organization.zone).to_date == organization.today
  end

  def actionable?(groups)
    GROUP_KEYS.any? { |key| Array(groups[key]).any? }
  end
end
