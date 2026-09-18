# frozen_string_literal: true

class Sync::RunNowJob < ApplicationJob
  queue_as :default

  def perform(organization_id)
    organization = Organization.find_by(id: organization_id)
    if organization.blank?
      Sync::State.clear_running!(organization_id)
      return
    end

    result = Sync::RunNow.execute(organization: organization)
    return if result.success?

    raise StandardError, result.errors
  end
end
