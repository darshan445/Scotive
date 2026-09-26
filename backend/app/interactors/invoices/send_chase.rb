# frozen_string_literal: true

# Invoices::SendChase Interactor
# Purpose: user-approved send on the last client thread. Requires a check-back date so a ghost returns to Needs you.
# Methods:
# - execute

class Invoices::SendChase
  include ExecuteMethodHelper
  include LogHelper
  include Cadence::HomeThreadSend

  def self.execute(organization:, invoice_id:, subject:, body:, wait_until: nil, client: Email::EmailClient.new)
    new(
      organization: organization,
      invoice_id: invoice_id,
      subject: subject,
      body: body,
      wait_until: wait_until,
      client: client
    ).execute
  end

  def initialize(organization:, invoice_id:, subject:, body:, wait_until:, client:)
    @organization = organization
    @invoice_id = invoice_id
    @subject = subject.to_s.strip
    @body = body.to_s.strip
    @wait_until = wait_until
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?
      raise_string_error("Subject is required") if subject.blank?
      raise_string_error("Body is required") if body.blank?

      outcome = nil
      Invoice.transaction do
        invoice = organization.invoices.lock.find_by(id: invoice_id)
        raise_string_error("Invoice not found") if invoice.blank?
        raise_string_error("This invoice is paid") if invoice.books_closed?
        raise_string_error("Client email is missing") if invoice.client&.primary_email.blank?
        raise_string_error("Check-back date is required") if parsed_wait.blank?
        raise_string_error("Check-back date must be today or later") if parsed_wait < organization.today

        draft = invoice.outbox_messages.where(status: "draft").order(created_at: :desc).first
        conversation = reply_thread_for(invoice, draft)
        raise_string_error("Home thread is missing") if conversation.blank?

        outcome = deliver_home_thread!(
          invoice: invoice,
          to: reply_address_for(invoice, conversation),
          cc: Array(invoice.cc_emails),
          subject: threaded_subject(conversation, subject),
          body: body,
          client: client,
          outbox: draft,
          conversation: conversation
        )
        invoice.outbox_messages.where(status: "scheduled").find_each do |row|
          row.update!(status: "cancelled", cancellation_reason: "human_sent")
        end
        apply_wait_until!(invoice, parsed_wait)
        outcome[:invoice] = Ledger::InvoicePayload.for(invoice.reload)
      end
      outcome
    end
  end

  private

  attr_reader :organization, :invoice_id, :subject, :body, :wait_until, :client

  def parsed_wait
    return if wait_until.blank?
    return wait_until.to_date if wait_until.respond_to?(:to_date) && !wait_until.is_a?(String)

    Date.parse(wait_until.to_s)
  rescue Date::Error, ArgumentError
    nil
  end
end
