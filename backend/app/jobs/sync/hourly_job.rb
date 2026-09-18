# frozen_string_literal: true

class Sync::HourlyJob < ApplicationJob
  queue_as :default

  def perform
    Organization.find_each do |organization|
      next unless organization.integrations.connected.exists?

      Sync::Start.execute(organization: organization)
    end
  end
end
