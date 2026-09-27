# frozen_string_literal: true

# Xero invoice list does not include the pay URL. GET /Invoices/{id}/OnlineInvoice does.
module Xero::InvoiceLinkFetch
  def attach_invoice_links!(integration, access_token, invoices)
    invoices.map { |payload| attach_invoice_link!(integration, access_token, payload) }
  end

  def attach_invoice_link!(integration, access_token, payload)
    return payload if payload["OnlineInvoiceUrl"].present? || payload["InvoiceLink"].present?

    id = payload["InvoiceID"].to_s
    return payload if id.blank?

    url = client.get_online_invoice_url(
      tenant_id: integration.external_account_id,
      access_token: access_token,
      id: id
    )
    return payload if url.blank?

    payload.merge("OnlineInvoiceUrl" => url)
  rescue Faraday::Error
    payload
  end
end
