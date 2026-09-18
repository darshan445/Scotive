# frozen_string_literal: true

# Admin::UserInvoices Interactor
# Purpose: invoice rows for one user (org-scoped) for ops QA.
# Methods:
# - execute

class Admin::UserInvoices
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(user_id:, limit: 100)
    new(user_id: user_id, limit: limit).execute
  end

  def initialize(user_id:, limit:)
    @user_id = user_id
    @limit = limit.to_i.clamp(1, 200)
  end

  def execute
    execute_log_and_return_open_struct do
      user = User.find_by(id: user_id)
      raise_string_error("User not found") if user.blank?

      invoices = user.organization.invoices
        .includes(:client, :integration, :invoice_state_transitions, invoice_conversations: { conversation: :messages })
        .order(due_date: :desc, created_at: :desc)
        .limit(limit)

      { invoices: invoices.map { |invoice| payload(invoice) } }
    end
  end

  private

  attr_reader :user_id, :limit

  def payload(invoice)
    Ledger::InvoicePayload.for(invoice).merge(
      id: invoice.id,
      source: invoice.integration&.provider,
      evidence_sentence: evidence_for(invoice)
    )
  end

  def evidence_for(invoice)
    quote = invoice.invoice_state_transitions.max_by(&:created_at)&.reason_quote
    return quote if quote.present?

    conversation = Ledger::InvoicePayload.primary_conversation(invoice)
    snippet = conversation&.messages&.max_by(&:sent_at)&.clean_body.to_s.strip
    snippet.presence&.truncate(400)
  end
end
