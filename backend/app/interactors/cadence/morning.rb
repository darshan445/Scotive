# frozen_string_literal: true

# Cadence::Morning Interactor
# Purpose: 08:00 local — enqueue cadence only in each org's timezone morning window.
# Methods:
# - execute

class Cadence::Morning
  include ExecuteMethodHelper
  include LogHelper

  def self.execute
    new.execute
  end

  def execute
    execute_log_and_return_open_struct do
      ran = 0
      Organization.find_each do |organization|
        next unless organization.integrations.connected.exists?
        next unless local_morning?(organization)

        Cadence::Schedule.execute(organization: organization)
        Sync::ApplyClock.execute(organization: organization)
        ran += 1
      end
      { ran: ran }
    end
  end

  private

  def local_morning?(organization)
    now = Time.current.in_time_zone(organization.zone)
    now.hour == 8 && now.min < 15
  end
end
