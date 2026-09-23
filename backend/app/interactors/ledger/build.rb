# frozen_string_literal: true

# Ledger::Build Interactor
# Purpose: Tenant-scoped open/history invoice list for the dashboard.
# Methods:
# - execute

class Ledger::Build
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      invoices = organization.invoices
        .includes(:organization, :client, :last_human_inbound_message, :invoice_chase_events, :outbox_messages, invoice_conversations: { conversation: :messages })
        .order(due_date: :asc, created_at: :asc)

      {
        invoices: invoices.map { |invoice| Ledger::InvoicePayload.for(invoice) },
        client_count: open_client_count
      }
    end
  end

  private

  attr_reader :organization

  def open_client_count
    organization.clients
      .joins(:invoices)
      .where(invoices: { organization_id: organization.id })
      .where("invoices.balance_remaining > 0")
      .distinct
      .count
  end
end
