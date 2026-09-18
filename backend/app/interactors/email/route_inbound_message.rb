# frozen_string_literal: true

# Email::RouteInboundMessage Interactor
# Purpose: Known-thread persist vs gated unknown match for one normalized message.
# Methods:
# - execute

class Email::RouteInboundMessage
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  OPEN_STATUSES = %w[unmatched invoiced overdue promised broken_promise disputed paid_unconfirmed partially_paid].freeze

  def self.execute(organization:, mailbox:, message:)
    new(organization: organization, mailbox: mailbox, message: message).execute
  end

  def initialize(organization:, mailbox:, message:)
    @organization = organization
    @mailbox = mailbox
    @message = message
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?
      raise_string_error("Mailbox is required") if mailbox.blank?
      raise_string_error("Message is required") if message.blank?

      conversation = organization.conversations.find_by(
        integration_id: mailbox.id,
        external_thread_id: message[:thread_id]
      )
      if conversation.present?
        persist_known!(conversation)
      else
        persist_unknown!
      end
    end
  end

  private

  attr_reader :organization, :mailbox, :message

  def persist_known!(conversation)
    owner_email = normalize_email(mailbox.account_name)
    persist_message!(conversation, message, owner_email, anchor: false)
    invoice_ids = conversation.invoice_conversations.pluck(:invoice_id)
    invoice_ids.each { |id| Email::EvaluateInvoiceStateJob.perform_later(id) }
    { routed: "known_thread", conversation_id: conversation.id, invoices: invoice_ids.size }
  end

  def persist_unknown!
    open_invoices = organization.invoices.where(current_ar_status: OPEN_STATUSES).includes(:client).to_a
    return { discarded: true, reason: "no_open_invoices" } if open_invoices.empty?

    clients = organization.clients.to_a
    client_hit = clients.find { |row| message_for_client?(message, row) }
    token_or_number = open_invoices.any? { |invoice| match_token?(invoice, message) || match_number?(invoice, message) }
    return { discarded: true, reason: "gated" } if client_hit.blank? && !token_or_number

    candidates = if client_hit
      open_invoices.select { |invoice| invoice.client_id == client_hit.id }
    else
      open_invoices
    end
    matched = candidates.select { |invoice| match_invoice?(invoice, message, candidates) }
    matched = open_invoices.select { |invoice| match_token?(invoice, message) || match_number?(invoice, message) } if matched.empty?
    return { discarded: true, reason: "no_invoice_match" } if matched.empty?

    matched.each do |invoice|
      persist_thread!(mailbox, invoice, message[:thread_id], [ message ], primary: !invoice_has_home_thread?(invoice))
      remember_sender!(invoice.client, message[:from])
      Email::EvaluateInvoiceStateJob.perform_later(invoice.id)
    end

    { routed: "unknown_match", invoices: matched.map(&:id) }
  end

  def remember_sender!(client_row, email)
    normalized = normalize_email(email)
    return if normalized.blank?

    client_row.associated_emails = merge_associated(client_row.associated_emails, normalized)
    client_row.primary_email = normalized if client_row.primary_email.blank?
    client_row.save!
  end

  def merge_associated(existing, email)
    (Array(existing) + [ email ]).map { |value| normalize_email(value) }.compact.uniq
  end
end
