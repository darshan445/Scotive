# frozen_string_literal: true

# Quickbooks::ApplyWebhook Interactor
# Purpose: Books-win accounting webhook — paid/partial/new invoice/void. No inline AI.
# Methods:
# - execute

class Quickbooks::ApplyWebhook
  include ExecuteMethodHelper
  include LogHelper
  include Quickbooks::BooksPersistence
  include Quickbooks::TokenRefresh

  def self.execute(webhook_event:, client: Quickbooks::QuickbookClient.new)
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
      name = payload["name"].to_s
      operation = payload["operation"].to_s
      if %w[Invoice Payment].exclude?(name)
        { skipped: true, reason: "ignored_entity" }
      elsif integration.blank?
        { skipped: true, reason: "unknown_realm" }
      else
        apply_entity!(name, operation, payload["id"].to_s)
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
      Integration.accounting.connected.find_by(provider: "qbo", external_account_id: realm_id)
  end

  def realm_id
    stringify(webhook_event.payload)["realmId"].to_s.presence || integration&.external_account_id
  end

  def apply_entity!(name, operation, remote_id)
    raise_string_error("QuickBooks entity id is missing") if remote_id.blank?

    if name == "Invoice" && operation.casecmp("delete").zero?
      return void_remote_invoice!(remote_id)
    end

    access_token = ensure_fresh_token!(integration)
    if name == "Payment"
      apply_payment!(access_token, remote_id)
    else
      apply_invoice!(access_token, remote_id)
    end
  end

  def apply_payment!(access_token, remote_id)
    payment = client.get_payment(realm_id: realm_id, access_token: access_token, id: remote_id)
    ids = linked_invoice_ids(payment)
    raise_string_error("QuickBooks payment has no linked invoices") if ids.empty?

    results = ids.map { |invoice_id| apply_invoice!(access_token, invoice_id) }
    { applied: "payment", invoices: results }
  rescue Faraday::Error => e
    handle_qbo_error!(e)
  end

  def apply_invoice!(access_token, remote_id)
    payload = client.get_invoice(realm_id: realm_id, access_token: access_token, id: remote_id)
    persist_one_invoice!(payload)
  rescue Faraday::Error => e
    return void_remote_invoice!(remote_id) if e.message.match?(/404/)

    handle_qbo_error!(e)
  end

  def persist_one_invoice!(payload)
    customer_id = payload.dig("CustomerRef", "value").to_s
    raise_string_error("QuickBooks invoice is missing a customer") if customer_id.blank?

    created = false
    invoice = nil
    ActiveRecord::Base.transaction do
      client_record = upsert_client!(integration, payload, fetch_customer_payload(customer_id))
      created = organization.invoices.where(integration_id: integration.id, external_id: payload["Id"].to_s).empty?
      upsert_invoice!(integration, client_record, payload, trigger_source: "books_webhook")
      invoice = organization.invoices.find_by!(integration_id: integration.id, external_id: payload["Id"].to_s)
    end
    enqueue_unmatched_thread!(invoice)

    { applied: "invoice", invoice_id: invoice.id, status: invoice.current_ar_status, created: created }
  end

  def enqueue_unmatched_thread!(invoice)
    return if invoice.invoice_conversations.exists?
    return if %w[paid voided].include?(invoice.current_ar_status)

    Email::FindInvoiceThreadJob.perform_later(invoice.id)
  end

  def void_remote_invoice!(remote_id)
    invoice = organization.invoices.where(integration_id: integration.id, external_id: remote_id).lock.first
    return { skipped: true, reason: "invoice_missing" } if invoice.blank?

    void_local_invoice!(invoice)
    { applied: "voided", invoice_id: invoice.id }
  end

  def fetch_customer_payload(customer_id)
    client.get_customer(realm_id: realm_id, access_token: integration.access_token, id: customer_id)
  rescue Faraday::Error
    {}
  end

  def linked_invoice_ids(payment)
    Array(payment["Line"]).flat_map do |line|
      Array(line["LinkedTxn"]).filter_map do |txn|
        txn["TxnId"].to_s if txn["TxnType"].to_s == "Invoice" && txn["TxnId"].present?
      end
    end.uniq
  end

  def ensure_fresh_token!(record)
    super
  rescue Faraday::Error => e
    handle_qbo_error!(e)
  end

  def handle_qbo_error!(error)
    mark_reauth!(integration) if qbo_grant_error?(error)
    raise_string_error("QuickBooks webhook apply failed")
  end

  def stringify(payload)
    payload.is_a?(Hash) ? payload.stringify_keys : {}
  end
end
