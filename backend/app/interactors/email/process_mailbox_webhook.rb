# frozen_string_literal: true

# Email::ProcessMailboxWebhook Interactor
# Purpose: Known-thread persist vs gated unknown match. Enqueue AI; no inline LLM.
# Methods:
# - execute

class Email::ProcessMailboxWebhook
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  def self.execute(webhook_event:, client: Email::EmailClient.new)
    new(webhook_event: webhook_event, client: client).execute
  end

  def initialize(webhook_event:, client:)
    @webhook_event = webhook_event
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Webhook event is required") if webhook_event.blank?

      if mailbox.blank? || organization.blank?
        { skipped: true, reason: "unknown_mailbox" }
      else
        message = load_message!
        if message.blank?
          { skipped: true, reason: "unreadable_message" }
        else
          validate_result(Email::RouteInboundMessage.execute(
            organization: organization,
            mailbox: mailbox,
            message: message
          )).data
        end
      end
    end
  end

  private

  attr_reader :webhook_event, :client

  def organization
    @organization ||= webhook_event.organization || mailbox&.organization
  end

  def mailbox
    return @mailbox if defined?(@mailbox)

    @mailbox = webhook_event.integration
    if @mailbox.blank?
      account_id = stringify(webhook_event.payload)["account_id"].to_s
      @mailbox = Integration.mailbox.connected.find_by(external_account_id: account_id) if account_id.present?
    end
    @mailbox
  end

  def load_message!
    payload = stringify(webhook_event.payload)
    email_id = payload["email_id"].presence
    raw = if email_id.present? && payload["is_complete"] == false
      client.get_email(email_id)
    elsif email_id.present? && payload["thread_id"].blank?
      client.get_email(email_id)
    else
      payload
    end
    normalize_message(stringify(raw))
  rescue Faraday::Error
    raise_string_error("Mailbox webhook fetch failed")
  end

  def stringify(payload)
    payload.is_a?(Hash) ? payload.stringify_keys : {}
  end
end
