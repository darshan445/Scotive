# frozen_string_literal: true

class Email::FindInvoiceThreadJob < ApplicationJob
  queue_as :default

  def perform(invoice_id)
    invoice = Invoice.find_by(id: invoice_id)
    return if invoice.blank?

    result = Email::FindInvoiceThread.execute(invoice: invoice)
    raise StandardError, result.errors unless result.success?
  end
end
