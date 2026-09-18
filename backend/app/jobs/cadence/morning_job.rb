# frozen_string_literal: true

class Cadence::MorningJob < ApplicationJob
  queue_as :default

  def perform
    Organization.find_each do |organization|
      next unless organization.integrations.connected.exists?

      Cadence::Schedule.execute(organization: organization)
    end
  end
end
