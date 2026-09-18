# frozen_string_literal: true

require "uri"

# Shared QBO client/invoice upsert used by historical import and accounting webhooks.
module Quickbooks::BooksPersistence
  PUBLIC_EMAIL_DOMAINS = %w[
    gmail.com googlemail.com yahoo.com ymail.com outlook.com hotmail.com
    live.com msn.com icloud.com me.com mac.com aol.com proton.me protonmail.com
  ].freeze

  def persist_books!(integration, invoices, customers_by_id, trigger_source: "books_sync")
    counts = { fetched: invoices.size, created: 0, updated: 0, merged: 0 }

    ActiveRecord::Base.transaction do
      invoices.each do |payload|
        customer_id = payload.dig("CustomerRef", "value").to_s
        next if customer_id.blank?

        client_record = upsert_client!(integration, payload, customers_by_id[customer_id])
        result = upsert_invoice!(integration, client_record, payload, trigger_source: trigger_source)
        counts[result] += 1
      end
    end

    counts
  end

  def upsert_client!(integration, invoice_payload, customer_payload)
    external_id = invoice_payload.dig("CustomerRef", "value").to_s
    customer = customer_payload.is_a?(Hash) ? customer_payload : {}
    email = customer.dig("PrimaryEmailAddr", "Address").presence ||
      invoice_payload.dig("BillEmail", "Address").presence
    email = normalize_email(email)
    cc = parse_emails(invoice_payload.dig("BillEmailCc", "Address"))
    bcc = parse_emails(invoice_payload.dig("BillEmailBcc", "Address"))

    record = organization.clients.find_or_initialize_by(integration_id: integration.id, external_id: external_id)
    record.organization = organization
    record.integration = integration
    record.name = customer["DisplayName"].presence ||
      invoice_payload.dig("CustomerRef", "name").presence ||
      "Customer #{external_id}"
    record.primary_email = email if email.present?
    record.domain = corporate_domain(record.primary_email) if record.domain.blank?
    record.associated_emails = merge_emails(record.associated_emails, [ email ] + cc + bcc)
    raise_string_error(record.errors.full_messages.to_sentence) unless record.save
    record
  end

  def upsert_invoice!(integration, client_record, payload, trigger_source: "books_sync")
    external_id = payload["Id"].to_s
    raise_string_error("QBO invoice is missing an id") if external_id.blank?

    invoice = organization.invoices.where(integration_id: integration.id, external_id: external_id).lock.first
    existed = invoice.present?
    invoice ||= organization.invoices.new(integration: integration, external_id: external_id, organization: organization)

    issue_date = parse_date(payload["TxnDate"]) || Date.current
    due_date = parse_date(payload["DueDate"]) || issue_date
    total = BigDecimal(payload["TotalAmt"].to_s)
    balance = BigDecimal(payload["Balance"].to_s)
    cc = parse_emails(payload.dig("BillEmailCc", "Address"))
    bcc = parse_emails(payload.dig("BillEmailBcc", "Address"))
    status = next_status(invoice, total, balance, due_date)
    previous_status = invoice.current_ar_status if existed

    invoice.assign_attributes(
      organization: organization,
      integration: integration,
      client: client_record,
      invoice_number: payload["DocNumber"].presence || external_id,
      issue_date: issue_date,
      due_date: due_date,
      currency: payload.dig("CurrencyRef", "value").presence || "USD",
      total_amount: total,
      balance_remaining: balance,
      pay_link_token: pay_link_token(payload),
      cc_emails: cc,
      bcc_emails: bcc,
      current_ar_status: status
    )
    invoice.active_promise_date = nil if status == "paid"
    invoice.needs_reply = false if status == "paid"
    raise_string_error(invoice.errors.full_messages.to_sentence) unless invoice.save

    if !existed || previous_status != status
      invoice.invoice_state_transitions.create!(
        from_status: existed ? previous_status : nil,
        to_status: status,
        trigger_source: trigger_source,
        created_at: Time.current
      )
    end

    cancel_pending_outbox!(invoice, "paid_in_books") if status == "paid"
    existed ? :updated : :created
  end

  def next_status(invoice, total, balance, due_date)
    return "paid" if balance <= 0
    return "partially_paid" if total.positive? && balance < total
    if invoice.persisted? && %w[promised disputed paid_unconfirmed broken_promise].include?(invoice.current_ar_status)
      return invoice.current_ar_status
    end

    due_date < Date.current ? "overdue" : "invoiced"
  end

  def pay_link_token(payload)
    url = payload["InvoiceLink"].presence
    return nil if url.blank?

    uri = URI.parse(url)
    token = uri.path.to_s.split("/").reject(&:blank?).last
    token.presence || uri.query
  rescue URI::InvalidURIError
    nil
  end

  def parse_date(value)
    return if value.blank?

    Date.parse(value.to_s)
  rescue Date::Error
    nil
  end

  def parse_emails(value)
    value.to_s.split(/[;,]/).map { |part| normalize_email(part) }.compact
  end

  def normalize_email(value)
    email = value.to_s.strip.downcase
    email.presence
  end

  def merge_emails(*lists)
    lists.flatten.map { |email| normalize_email(email) }.compact.uniq
  end

  def corporate_domain(email)
    host = email.to_s.split("@").last.to_s.downcase
    return if host.blank? || PUBLIC_EMAIL_DOMAINS.include?(host)

    host
  end

  def cancel_pending_outbox!(invoice, reason)
    return unless OutboxMessage.table_exists?

    OutboxMessage.cancel_pending_for!(invoice, reason)
  end

  def void_local_invoice!(invoice, trigger_source: "books_webhook")
    previous = invoice.current_ar_status
    return invoice if previous == "voided"

    invoice.update!(current_ar_status: "voided", balance_remaining: 0, needs_reply: false, active_promise_date: nil)
    invoice.invoice_state_transitions.create!(
      from_status: previous,
      to_status: "voided",
      trigger_source: trigger_source,
      created_at: Time.current
    )
    cancel_pending_outbox!(invoice, "invoice_voided")
    invoice
  end
end
