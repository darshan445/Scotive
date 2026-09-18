# frozen_string_literal: true

# Invoices::BuildConversation Interactor
# Purpose: Invoice + thread messages for the dashboard drawer.
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
        :client,
        :invoice_state_transitions,
        invoice_conversations: { conversation: :messages }
      ).find_by(id: invoice_id)
      raise_string_error("Invoice not found") if invoice.blank?

      conversation = Ledger::InvoicePayload.primary_conversation(invoice)
      messages = conversation ? conversation.messages.sort_by(&:sent_at) : []
      {
        invoice: Ledger::InvoicePayload.for(invoice),
        thread_id: conversation&.external_thread_id,
        client_ever_replied: messages.any? { |message| message.direction == "client_to_user" },
        messages: messages.map { |message| serialize_message(message, conversation) }
      }
    end
  end

  private

  attr_reader :organization, :invoice_id

  def serialize_message(message, conversation)
    {
      id: message.id,
      direction: message.direction == "user_to_client" ? "you" : "them",
      date: message.sent_at.iso8601,
      body: message.clean_body,
      subject: conversation&.subject,
      from: message.from_address
    }
  end
end
