# frozen_string_literal: true

class Webhooks::ReplayPendingJob < ApplicationJob
  queue_as :default

  def perform
    Webhooks::ReplayPending.execute
  end
end
