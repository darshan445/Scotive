# frozen_string_literal: true

# Settings::Timezones Interactor
# Purpose: IANA timezone list for the Settings picker.
# Methods:
# - execute

class Settings::Timezones
  include ExecuteMethodHelper
  include LogHelper

  def self.execute
    new.execute
  end

  def execute
    execute_log_and_return_open_struct do
      rows = ActiveSupport::TimeZone.all.map do |zone|
        { value: zone.tzinfo.identifier, label: zone.to_s }
      end
      { timezones: rows.uniq { |row| row[:value] } }
    end
  end
end
