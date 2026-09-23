# frozen_string_literal: true

# Invoices::BuildConversation Interactor
# Purpose: Invoice + a single newest-first conversation for the dashboard drawer.
# Methods:
# - execute

class Invoices::BuildConversation
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:, invoice_id:)
    new(organization: organization, invoice_id: invoice_id).execute
  end

  def initialize(organization:, invoice_id:)
    @organization = organization
    @invoice_id = invoice_id
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      invoice = organization.invoices.includes(
        :organization,
        :client,
        :last_human_inbound_message,
        :invoice_chase_events,
        :outbox_messages,
        invoice_conversations: { conversation: :messages }
      ).find_by(id: invoice_id)
      raise_string_error("Invoice not found") if invoice.blank?

      threads = serialize_threads(invoice)
      home = threads.find { |thread| thread[:is_primary] } || threads.first
      messages = uniqued_messages(Array(home&.dig(:messages)))
        .sort_by { |message| message[:date].to_s }
        .reverse
      {
        invoice: Ledger::InvoicePayload.for(invoice),
        thread_id: home&.dig(:thread_id),
        client_ever_replied: messages.any? { |message| message[:direction] == "them" },
        messages: messages,
        split_quote: split_quote_for(threads, home),
        threads: threads
      }
    end
  end

  private

  attr_reader :organization, :invoice_id

  def serialize_threads(invoice)
    invoice.invoice_conversations.sort_by { |link| thread_sort_key(link) }.filter_map do |link|
      conversation = link.conversation
      next if conversation.blank?

      thread_messages = conversation.messages.sort_by(&:sent_at)
      {
        thread_id: conversation.external_thread_id,
        subject: conversation.subject,
        is_primary: link.is_primary?,
        client_ever_replied: thread_messages.any? { |message| message.direction == "client_to_user" },
        messages: uniqued_messages(thread_messages.map { |message| serialize_message(message, conversation) })
      }
    end
  end

  def split_quote_for(threads, home)
    extras = threads.reject { |thread| thread[:thread_id] == home&.dig(:thread_id) }
    inbound = extras.flat_map { |thread| Array(thread[:messages]) }
      .select { |message| message[:direction] == "them" }
      .max_by { |message| message[:date].to_s }
    return if inbound.blank?

    {
      quote: inbound[:body].to_s.strip.truncate(220),
      date: inbound[:date],
      subject: inbound[:subject],
      thread_id: inbound[:thread_id]
    }
  end

  def uniqued_messages(messages)
    messages.uniq { |message| [ message[:direction], message[:date].to_s, message[:body].to_s[0, 240] ] }
  end

  def thread_sort_key(link)
    first_at = link.conversation.messages.map(&:sent_at).compact.min || Time.zone.at(0)
    [ link.is_primary? ? 0 : 1, first_at ]
  end

  def serialize_message(message, conversation)
    {
      id: message.id,
      direction: message.direction == "user_to_client" ? "you" : "them",
      date: message.sent_at.iso8601,
      body: message.clean_body,
      subject: conversation&.subject,
      from: message.from_address,
      thread_id: conversation&.external_thread_id
    }
  end
end
