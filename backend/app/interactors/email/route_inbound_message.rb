# frozen_string_literal: true

# Email::RouteInboundMessage Interactor
# Purpose: Known-thread persist vs Pass 1 / Pass 2 unknown match for one message.
# Methods:
# - execute

class Email::RouteInboundMessage
  include ExecuteMethodHelper
  include LogHelper
  include Email::MailboxThreadPersistence

  def self.execute(organization:, mailbox:, message:, llm: Email::LlmClient.new, context_messages: nil)
    new(organization: organization, mailbox: mailbox, message: message, llm: llm, context_messages: context_messages).execute
  end

  def initialize(organization:, mailbox:, message:, llm:, context_messages:)
    @organization = organization
    @mailbox = mailbox
    @message = message
    @llm = llm
    @context_messages = Array(context_messages)
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

  attr_reader :organization, :mailbox, :message, :llm, :context_messages

  def persist_known!(conversation)
    owner_email = normalize_email(mailbox.account_name)
    persist_message!(conversation, message, owner_email, anchor: false)
    invoice_ids = conversation.invoice_conversations.pluck(:invoice_id)
    invoice_ids.each { |id| Email::EvaluateInvoiceStateJob.perform_later(id) }
    { routed: "known_thread", conversation_id: conversation.id, invoices: invoice_ids.size }
  end

  def persist_unknown!
    open_invoices = organization.invoices.books_open.includes(:client).to_a
    return { discarded: true, reason: "no_open_invoices" } if open_invoices.empty?
    return { discarded: true, reason: "automatic_reply" } if automatic_reply?(message)

    clients = organization.clients.to_a
    client_hit = clients.find { |row| message_for_client?(message, row) }
    named = open_invoices.select { |invoice| match_number?(invoice, message) }
    toked = open_invoices.select { |invoice| match_token?(invoice, message) }
    return { discarded: true, reason: "gated" } if client_hit.blank? && named.empty? && toked.empty?

    targets = resolve_unknown_targets(client_hit, open_invoices, named)
    return { discarded: true, reason: "no_invoice_match" } if targets.empty?

    targets.each do |invoice|
      persist_thread!(mailbox, invoice, message[:thread_id], [ message ], primary: !invoice_has_home_thread?(invoice))
      remember_sender!(invoice.client, message[:from])
      Email::EvaluateInvoiceStateJob.perform_later(invoice.id)
    end

    { routed: "unknown_match", invoices: targets.map(&:id) }
  end

  def resolve_unknown_targets(client_hit, open_invoices, named)
    pool = client_hit ? open_invoices.select { |invoice| invoice.client_id == client_hit.id } : open_invoices
    scoped_named = named.select { |invoice| pool.map(&:id).include?(invoice.id) }
    scoped_named = named if scoped_named.empty? && named.any?
    return scoped_named if scoped_named.any?

    seeded = pass_one_invoices([ message ], pool)
    return seeded if seeded.any?
    return [] if client_hit.blank?
    return [] unless invoice_payment_intent?([ message ])

    pass_two_invoices([ message ], pool, pass_two_context, normalize_email(mailbox.account_name))
  end

  def pass_two_context
    context_messages.presence || [ message ]
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
