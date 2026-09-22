# frozen_string_literal: true

# Webhooks::ReplayPending Interactor
# Purpose: Re-enqueue webhook_events still pending after a lost Sidekiq job.
# Methods:
# - execute

class Webhooks::ReplayPending
  include ExecuteMethodHelper
  include LogHelper

  BATCH = 200

  def self.execute(organization: nil)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      scope = WebhookEvent.where(status: "pending").order(:created_at)
      scope = scope.where(organization_id: organization.id) if organization.present?
      ids = scope.limit(BATCH).pluck(:id)
      ids.each { |id| Webhooks::ProcessEventJob.perform_later(id) }
      { enqueued: ids.size }
    end
  end

  private

  attr_reader :organization
end
