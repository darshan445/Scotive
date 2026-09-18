# frozen_string_literal: true

# Clients::Show Interactor
# Purpose: One client by email — identities, invoices, payment-behavior stats.
# Methods:
# - execute

class Clients::Show
  include ExecuteMethodHelper
  include LogHelper

  OPEN_STATUSES = Clients::Index::OPEN_STATUSES

  def self.execute(organization:, email:)
    new(organization: organization, email: email).execute
  end

  def initialize(organization:, email:)
    @organization = organization
    @email = email.to_s.strip.downcase
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?
      raise_string_error("Client email is required") if email.blank?

      records = matching_clients
      raise_string_error("Client not found") if records.empty?

      invoices = organization.invoices.where(client_id: records.map(&:id))
        .includes(:client, :invoice_state_transitions, invoice_conversations: { conversation: :messages })
        .order(due_date: :desc)

      {
        email: email,
        name: records.map(&:name).find(&:present?),
        total_open: open_total(invoices),
        totals_by_currency: open_by_currency(invoices),
        identities: identities(records, invoices),
        invoices: invoices.map { |invoice| Ledger::InvoicePayload.for(invoice) },
        stats: stats_for(invoices)
      }
    end
  end

  private

  attr_reader :organization, :email

  def matching_clients
    organization.clients.select do |client|
      normalize(client.primary_email) == email ||
        Array(client.associated_emails).any? { |value| normalize(value) == email }
    end
  end

  def open_invoices(invoices)
    invoices.select { |invoice| OPEN_STATUSES.include?(invoice.current_ar_status) }
  end

  def open_total(invoices)
    open_invoices(invoices).sum { |invoice| invoice.balance_remaining.to_f }
  end

  def open_by_currency(invoices)
    totals = Hash.new(0.0)
    open_invoices(invoices).each do |invoice|
      totals[invoice.currency.to_s.upcase] += invoice.balance_remaining.to_f
    end
    totals
  end

  def identities(clients, invoices)
    emails = clients.flat_map do |client|
      [ client.primary_email ] + Array(client.associated_emails)
    end
    emails += invoices.flat_map { |invoice| Array(invoice.cc_emails) + Array(invoice.bcc_emails) }
    counts = Hash.new(0)
    invoices.each do |invoice|
      invoice.invoice_conversations.each do |link|
        conversation = link.conversation
        next if conversation.blank?

        conversation.messages.each do |message|
          counts[normalize(message.from_address)] += 1 if message.from_address.present?
        end
      end
    end
    emails.map { |value| normalize(value) }.compact.uniq.sort.map do |row|
      { email: row, message_count: counts[row] }
    end
  end

  def stats_for(invoices)
    paid = invoices.select { |invoice| invoice.current_ar_status == "paid" }
    lateness = paid.filter_map do |invoice|
      paid_on = paid_on_date(invoice)
      next unless paid_on && invoice.due_date

      (paid_on - invoice.due_date).to_i
    end
    promised = invoices.select { |invoice| invoice.invoice_state_transitions.any? { |row| row.to_status == "promised" } }
    kept = promised.count { |invoice| invoice.current_ar_status == "paid" }
    avg = lateness.any? ? (lateness.sum.to_f / lateness.size).round : nil
    {
      payment_cycles: paid.size,
      avg_days_late: avg,
      promise_total: promised.size,
      promise_kept: kept,
      promise_keep_rate: promised.empty? ? nil : (kept.to_f / promised.size),
      risk_hint: risk_hint(avg, paid.size)
    }
  end

  def paid_on_date(invoice)
    invoice.invoice_state_transitions.select { |row| row.to_status == "paid" }
      .max_by(&:created_at)&.created_at&.to_date || invoice.updated_at&.to_date
  end

  def risk_hint(avg_days_late, cycles)
    return "on_time" if cycles.zero? || avg_days_late.nil?
    return "risky" if avg_days_late >= 14
    return "slow" if avg_days_late >= 3

    "on_time"
  end

  def normalize(value)
    value.to_s.strip.downcase.presence
  end
end
