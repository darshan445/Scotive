# frozen_string_literal: true

# Clients::Index Interactor
# Purpose: Client list with open balances for the clients page.
# Methods:
# - execute

class Clients::Index
  include ExecuteMethodHelper
  include LogHelper

  OPEN_BOOKS = Invoice::OPEN_BOOKS

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      { clients: grouped_clients }
    end
  end

  private

  attr_reader :organization

  def grouped_clients
    clients = organization.clients.includes(:invoices).to_a
    rows = clients.filter_map { |client| serialize_client(client) }
    rows.sort_by { |row| -row[:open_amount].to_f }
  end

  def serialize_client(client)
    email = client.primary_email.to_s.downcase.presence
    return if email.blank?

    invoices = client.invoices.to_a
    open = invoices.select(&:books_open?)
    by_currency = Hash.new(0.0)
    open.each do |invoice|
      by_currency[invoice.currency.to_s.upcase] += invoice.balance_remaining.to_f
    end
    {
      email: email,
      name: client.name,
      invoice_count: invoices.size,
      open_amount: by_currency.values.sum,
      open_by_currency: by_currency,
      last_activity: invoices.map(&:updated_at).compact.max&.iso8601
    }
  end
end
