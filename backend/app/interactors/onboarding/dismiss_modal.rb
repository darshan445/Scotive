# frozen_string_literal: true

# Onboarding::DismissModal Interactor
# Purpose: Persist that the first-visit cadence explainer was dismissed.
# Methods:
# - execute

class Onboarding::DismissModal
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

      organization.update!(onboarding_modal_dismissed: true)
      { onboarding_modal_dismissed: true }
    end
  end

  private

  attr_reader :organization
end
