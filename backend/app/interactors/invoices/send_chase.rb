# frozen_string_literal: true

# Invoices::SendChase Interactor
# Purpose: user-approved send on the Home Thread. Books-paid still blocks; other cadence guards do not.
# Methods:
# - execute

class Invoices::SendChase
  include ExecuteMethodHelper
  include LogHelper
  include Cadence::HomeThreadSend

  def self.execute(organization:, invoice_id:, subject:, body:, client: Email::EmailClient.new)
    new(organization: organization, invoice_id: invoice_id, subject: subject, body: body, client: client).execute
  end

  def initialize(organization:, invoice_id:, subject:, body:, client:)
    @organization = organization
    @invoice_id = invoice_id
    @subject = subject.to_s.strip
    @body = body.to_s.strip
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
        raise_string_error("This invoice is paid") if invoice.balance_remaining.to_d <= 0 || %w[paid voided].include?(invoice.current_ar_status)
        raise_string_error("Client email is missing") if invoice.client&.primary_email.blank?

        draft = invoice.outbox_messages.where(status: "draft").order(created_at: :desc).first
        outcome = deliver_home_thread!(
          invoice: invoice,
          to: invoice.client.primary_email,
          cc: Array(invoice.cc_emails),
          subject: subject,
          body: body,
          client: client,
          outbox: draft
        )
        invoice.outbox_messages.where(status: "scheduled").find_each do |row|
          row.update!(status: "cancelled", cancellation_reason: "human_sent")
        end
        outcome[:invoice] = Ledger::InvoicePayload.for(invoice.reload)
      end
      outcome
    end
  end

  private

  attr_reader :organization, :invoice_id, :subject, :body, :client
end
