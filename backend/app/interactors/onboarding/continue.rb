# frozen_string_literal: true

# Onboarding::Continue Interactor
# Purpose: Advance off the connect screen once invoicing, import, and mailbox are ready.
# Methods:
# - execute

class Onboarding::Continue
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

      state = validate_result(Onboarding::BuildState.execute(organization: organization)).data
      raise_string_error("Connect invoicing first") unless state[:qbo_connected] || state[:xero_connected]
      raise_string_error("Import invoices before continuing") if state[:last_invoice_import_at].blank?
      raise_string_error("Connect Gmail or Outlook first") unless state[:gmail_connected]
      raise_string_error("Match conversations before continuing") if state[:qbo_pipeline].blank?

      { next: "dashboard" }
    end
  end

  private

  attr_reader :organization
end
