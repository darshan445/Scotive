# frozen_string_literal: true

# Onboarding::RecordQboStep Interactor
# Purpose: Acknowledge the frontend QBO-connected step (no ingest yet).
# Methods:
# - execute

class Onboarding::RecordQboStep
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:, action: nil)
    new(organization: organization, action: action).execute
  end

  def initialize(organization:, action:)
    @organization = organization
    @action = action.to_s
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      { recorded: true, action: action.presence || "connected" }
    end
  end

  private

  attr_reader :organization, :action
end
