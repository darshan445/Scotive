# frozen_string_literal: true

# Sync::Start Interactor
# Purpose: Fast-ack Sync Now — set running flag and enqueue the master job.
# Methods:
# - execute

class Sync::Start
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

      if Sync::State.running?(organization.id)
        status_payload("already_running")
      else
        Sync::State.mark_running!(organization.id)
        Sync::RunNowJob.perform_later(organization.id)
        status_payload(nil)
      end
    end
  end

  private

  attr_reader :organization

  def status_payload(skipped)
    validate_result(Sync::Status.execute(organization: organization)).data.merge(
      accepted: true,
      skipped: skipped
    )
  end
end
