# frozen_string_literal: true

class StoreFriendlyRemindersAsSlots < ActiveRecord::Migration[8.0]
  DEFAULT = {
    "before_due" => { "enabled" => true, "days" => 3 },
    "on_due" => { "enabled" => true },
    "overdue" => { "enabled" => true, "days" => 7 }
  }.freeze

  def up
    change_column_default :organizations, :escalation_offsets, from: [ -3, 0, 7 ], to: DEFAULT
    Organization.reset_column_information
    Organization.find_each do |organization|
      organization.update_columns(
        escalation_offsets: Organization.normalize_friendly_reminders(organization.escalation_offsets)
      )
    end
  end

  def down
    change_column_default :organizations, :escalation_offsets, from: DEFAULT, to: [ -3, 0, 7 ]
    Organization.reset_column_information
    Organization.find_each do |organization|
      offsets = organization.enabled_ladder.map { |row| row[:offset] }
      offsets = [ -3, 0, 7 ] if offsets.size != 3
      organization.update_columns(escalation_offsets: offsets)
    end
  end
end
