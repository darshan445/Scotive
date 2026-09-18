# frozen_string_literal: true

# Quickbooks::PipelineStatus Interactor
# Purpose: Expose mailbox match progress for the connect-screen pipeline bar.
# Methods:
# - execute

class Quickbooks::PipelineStatus
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

      mailbox = organization.integrations.mailbox.connected.where.not(sync_cursor: nil).first
      { pipeline: pipeline_for(mailbox) }
    end
  end

  private

  attr_reader :organization

  def pipeline_for(mailbox)
    return if mailbox.blank?

    {
      status: "complete",
      phase: "matching"
    }
  end
end
