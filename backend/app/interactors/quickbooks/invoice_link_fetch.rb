# frozen_string_literal: true

# QBO query does not return InvoiceLink. GET /invoice/{id}?include=invoiceLink does.
module Quickbooks::InvoiceLinkFetch
  def attach_invoice_links!(integration, access_token, invoices)
    invoices.map { |payload| attach_invoice_link!(integration, access_token, payload) }
  end

  def attach_invoice_link!(integration, access_token, payload)
    return payload if payload["InvoiceLink"].present?

    id = payload["Id"].to_s
    return payload if id.blank?

    full = client.get_invoice(
      realm_id: integration.external_account_id,
      access_token: access_token,
      id: id
    )
    link = full.is_a?(Hash) ? full["InvoiceLink"].presence : nil
    return payload if link.blank?

    payload.merge("InvoiceLink" => link)
  rescue Faraday::Error
    payload
  end
end
