# frozen_string_literal: true

class DropFirmOffsetAndFollowUpInterval < ActiveRecord::Migration[8.0]
  def up
    remove_column :organizations, :follow_up_interval_days
    change_column_default :organizations, :escalation_offsets, from: [ -3, 0, 7, 9 ], to: [ -3, 0, 7 ]
    Organization.reset_column_information
    Organization.find_each do |organization|
      values = Array(organization.escalation_offsets).first(3)
      organization.update_columns(escalation_offsets: values.size == 3 ? values : [ -3, 0, 7 ])
    end
  end

  def down
    add_column :organizations, :follow_up_interval_days, :integer, null: false, default: 3
    change_column_default :organizations, :escalation_offsets, from: [ -3, 0, 7 ], to: [ -3, 0, 7, 9 ]
    Organization.reset_column_information
    Organization.find_each do |organization|
      values = Array(organization.escalation_offsets)
      next if values.size >= 4

      organization.update_columns(escalation_offsets: (values + [ 9 ]).first(4))
    end
  end
end
