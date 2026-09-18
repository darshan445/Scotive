# frozen_string_literal: true

# Settings::Show Interactor
# Purpose: org chase + timezone settings for the Settings page.
# Methods:
# - execute

class Settings::Show
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

      Settings::Serialize.payload(organization)
    end
  end

  private

  attr_reader :organization
end
