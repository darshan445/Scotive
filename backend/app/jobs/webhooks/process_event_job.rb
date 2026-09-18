# frozen_string_literal: true

class Webhooks::ProcessEventJob < ApplicationJob
  queue_as :default

  def perform(webhook_event_id)
    event = WebhookEvent.find_by(id: webhook_event_id)
    return if event.blank? || event.status == "processed"

    result = Webhooks::ProcessEvent.execute(webhook_event: event)
    return if result.success?

    event.update!(status: "failed", error_message: Array(result.errors).join(", "))
    raise StandardError, result.errors
  end
end
