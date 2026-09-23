# frozen_string_literal: true

class AddOnboardingModalDismissedToOrganizations < ActiveRecord::Migration[8.1]
  def change
    add_column :organizations, :onboarding_modal_dismissed, :boolean, null: false, default: false
  end
end
