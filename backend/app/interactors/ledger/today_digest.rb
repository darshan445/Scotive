# frozen_string_literal: true

# Ledger::TodayDigest Interactor
# Purpose: Needs you rows only. Opening Scotive is the reminder.
# Methods:
# - execute

class Ledger::TodayDigest
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

      {
        needs_you: needs_you_invoices.map { |invoice| Ledger::InvoicePayload.for(invoice) }
      }
    end
  end

  private

  attr_reader :organization

  def needs_you_invoices
    organization.invoices.books_open
      .includes(:client, :invoice_chase_events, invoice_conversations: :conversation)
      .find_each
      .select { |invoice| invoice.list_bucket == "needs_you" }
  end
end
