# frozen_string_literal: true

# Xero::ApplyWebhook Interactor
# Purpose: Books-win accounting webhook — paid/partial/new invoice/void. No inline AI.
# Methods:
# - execute

class Xero::ApplyWebhook
  include ExecuteMethodHelper
  include LogHelper
  include Xero::BooksSync

  def self.execute(webhook_event:, client: Xero::XeroClient.new)
    new(webhook_event: webhook_event, client: client).execute
  end

  def initialize(webhook_event:, client:)
    @webhook_event = webhook_event
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Webhook event is required") if webhook_event.blank?

      payload = stringify(webhook_event.payload)
      category = payload["eventCategory"].to_s.upcase
      if category != "INVOICE"
        { skipped: true, reason: "ignored_entity" }
      elsif integration.blank?
        { skipped: true, reason: "unknown_tenant" }
      else
        apply_invoice!(payload["resourceId"].to_s)
      end
    end
  end

  private

  attr_reader :webhook_event, :client

  def organization
    @organization ||= webhook_event.organization || integration&.organization
  end

  def integration
    @integration ||= webhook_event.integration ||
      Integration.accounting.connected.find_by(provider: "xero", external_account_id: tenant_id)
  end

  def tenant_id
    stringify(webhook_event.payload)["tenantId"].to_s.presence || integration&.external_account_id
  end

  def apply_invoice!(remote_id)
    raise_string_error("Xero invoice id is missing") if remote_id.blank?

    access_token = ensure_fresh_token!(integration)
    payload = client.get_invoice(tenant_id: tenant_id, access_token: access_token, id: remote_id)
    if Xero::InvoiceMapper.voided?(payload)
      void_remote_invoice!(remote_id)
    elsif !Xero::InvoiceMapper.sales_invoice?(payload)
      { skipped: true, reason: "not_sales_invoice" }
    else
      persist_one_invoice!(attach_invoice_link!(integration, access_token, payload))
    end
  rescue Faraday::Error => e
    if e.message.match?(/404/)
      void_remote_invoice!(remote_id)
    else
      handle_xero_error!(e)
    end
  end

  def persist_one_invoice!(payload)
    mapped = Xero::InvoiceMapper.to_books_invoice(payload)
    customer_id = mapped.dig("CustomerRef", "value").to_s
    raise_string_error("Xero invoice is missing a contact") if customer_id.blank?

    created = false
    invoice = nil
    ActiveRecord::Base.transaction do
      client_record = upsert_client!(integration, mapped, fetch_customer_payload(customer_id))
      created = organization.invoices.where(integration_id: integration.id, external_id: mapped["Id"].to_s).empty?
      upsert_invoice!(integration, client_record, mapped, trigger_source: "books_webhook")
      invoice = organization.invoices.find_by!(integration_id: integration.id, external_id: mapped["Id"].to_s)
    end
    enqueue_unmatched_thread!(invoice)

    { applied: "invoice", invoice_id: invoice.id, status: invoice.books_status, created: created }
  end

  def enqueue_unmatched_thread!(invoice)
    return if invoice.invoice_conversations.exists?
    return if invoice.books_closed?

    Email::FindInvoiceThreadJob.perform_later(invoice.id)
  end

  def void_remote_invoice!(remote_id)
    invoice = organization.invoices.where(integration_id: integration.id, external_id: remote_id).lock.first
    return { skipped: true, reason: "invoice_missing" } if invoice.blank?

    void_local_invoice!(invoice)
    { applied: "voided", invoice_id: invoice.id }
  end

  def fetch_customer_payload(customer_id)
    raw = client.get_contact(
      tenant_id: tenant_id,
      access_token: integration.access_token,
      id: customer_id
    )
    Xero::InvoiceMapper.to_books_customer(raw)
  rescue Faraday::Error
    {}
  end

  def ensure_fresh_token!(record)
    super
  rescue Faraday::Error => e
    handle_xero_error!(e)
  end

  def handle_xero_error!(error)
    mark_reauth!(integration) if xero_grant_error?(error)
    raise_string_error("Xero webhook apply failed")
  end

  def stringify(payload)
    payload.is_a?(Hash) ? payload.stringify_keys : {}
  end
end
