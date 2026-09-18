# frozen_string_literal: true

# Webhooks::ProcessEvent Interactor
# Purpose: Dispatch one persisted webhook_event to accounting or mailbox processors.
# Methods:
# - execute

class Webhooks::ProcessEvent
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(webhook_event:)
    new(webhook_event: webhook_event).execute
  end

  def initialize(webhook_event:)
    @webhook_event = webhook_event
  end

  def execute
    execute_log_and_return_open_struct do
      if webhook_event.status == "processed"
        { skipped: true }
      else
        outcome = dispatch!(webhook_event)
        webhook_event.update!(status: "processed", processed_at: Time.current, error_message: nil)
        outcome
      end
    end
  end

  private

  attr_reader :webhook_event

  def dispatch!(event)
    case event.provider
    when "qbo"
      validate_result(Quickbooks::ApplyWebhook.execute(webhook_event: event)).data
    when "gmail", "outlook"
      validate_result(Email::ProcessMailboxWebhook.execute(webhook_event: event)).data
    else
      raise_string_error("Unknown webhook provider")
    end
  end
end
