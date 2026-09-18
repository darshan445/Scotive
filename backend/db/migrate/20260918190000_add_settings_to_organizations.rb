# frozen_string_literal: true

class AddSettingsToOrganizations < ActiveRecord::Migration[8.1]
  def change
    add_column :organizations, :time_zone, :string, null: false, default: "UTC"
    add_column :organizations, :friendly_auto_send, :boolean, null: false, default: true
    add_column :organizations, :escalation_offsets, :jsonb, null: false, default: [ -3, 0, 7, 9 ]
    add_column :organizations, :follow_up_interval_days, :integer, null: false, default: 3
    add_column :organizations, :daily_digest_enabled, :boolean, null: false, default: false
    add_column :organizations, :daily_digest_hour, :integer, null: false, default: 9
  end
end
