# frozen_string_literal: true

class Cadence::MorningJob < ApplicationJob
  queue_as :default

  def perform
    Cadence::Morning.execute
  end
end
