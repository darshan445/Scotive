# frozen_string_literal: true

class Email::RenewMailboxWebhooksJob < ApplicationJob
  queue_as :default

  def perform
    Email::RenewMailboxWebhooks.execute
  end
end
