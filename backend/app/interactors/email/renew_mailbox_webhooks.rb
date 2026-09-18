# frozen_string_literal: true

# Email::RenewMailboxWebhooks Interactor
# Purpose: Day-5 Unipile webhook renewal — stamp webhook_expires_at (7-day Gmail watch lease).
# Methods:
# - execute

class Email::RenewMailboxWebhooks
  include ExecuteMethodHelper
  include LogHelper

  RENEW_WHEN_WITHIN = 2.days

  def self.execute(client: Email::EmailClient.new)
    new(client: client).execute
  end

  def initialize(client:)
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      renewed = 0
      skipped = 0
      Organization.find_each do |organization|
        next unless due_mailboxes(organization).exists?

        result = Email::EnsureMailboxWebhook.execute(organization: organization, client: client)
        if result.success? && result.data[:registered]
          renewed += 1
        else
          skipped += 1
        end
      end
      { renewed: renewed, skipped: skipped }
    end
  end

  private

  attr_reader :client

  def due_mailboxes(organization)
    organization.integrations.mailbox.connected.where(
      "webhook_expires_at IS NULL OR webhook_expires_at <= ?",
      RENEW_WHEN_WITHIN.from_now
    )
  end
end
