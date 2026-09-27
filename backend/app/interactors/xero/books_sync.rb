# frozen_string_literal: true

# Persist Xero invoices through the shared books upsert, including voids.
module Xero::BooksSync
  include Quickbooks::BooksPersistence
  include Xero::InvoiceLinkFetch
  include Xero::TokenRefresh

  def persist_xero_books!(integration, invoices, contacts_by_id, trigger_source: "books_sync")
    mapped = []
    invoices.each do |payload|
      next unless Xero::InvoiceMapper.sales_invoice?(payload)
      next if Xero::InvoiceMapper.voided?(payload) && void_mapped!(integration, payload)

      mapped << Xero::InvoiceMapper.to_books_invoice(payload)
    end
    persist_books!(integration, mapped, contacts_by_id, trigger_source: trigger_source)
  end

  def void_mapped!(integration, payload)
    remote_id = payload["InvoiceID"].to_s
    invoice = organization.invoices.where(integration_id: integration.id, external_id: remote_id).lock.first
    if invoice.present?
      void_local_invoice!(invoice, trigger_source: "books_sync")
    end
    true
  end

  def contacts_by_id_from(access_token, invoices)
    ids = invoices.filter_map { |invoice| invoice.dig("Contact", "ContactID").presence }.uniq
    return {} if ids.empty?

    client.query_contacts(
      tenant_id: integration.external_account_id,
      access_token: access_token,
      ids: ids
    ).each_with_object({}) do |row, memo|
      mapped = Xero::InvoiceMapper.to_books_customer(row)
      memo[mapped["Id"]] = mapped if mapped["Id"].present?
    end
  rescue Faraday::Error
    {}
  end
end
