# frozen_string_literal: true

# Maps Xero Invoice / Contact payloads onto the QBO-shaped hashes BooksPersistence expects.
module Xero::InvoiceMapper
  VOID_STATUSES = %w[VOIDED DELETED].freeze

  def self.to_books_invoice(invoice)
    contact = invoice.is_a?(Hash) ? (invoice["Contact"] || {}) : {}
    emails = contact_person_emails(contact)
    {
      "Id" => invoice["InvoiceID"].to_s,
      "DocNumber" => invoice["InvoiceNumber"].presence || invoice["InvoiceID"].to_s,
      "TxnDate" => iso_date(invoice["DateString"].presence || invoice["Date"]),
      "DueDate" => iso_date(invoice["DueDateString"].presence || invoice["DueDate"]),
      "TotalAmt" => invoice["Total"],
      "Balance" => invoice["AmountDue"],
      "CurrencyRef" => { "value" => invoice["CurrencyCode"].presence || "USD" },
      "CustomerRef" => { "value" => contact["ContactID"].to_s, "name" => contact["Name"] },
      "BillEmail" => { "Address" => contact["EmailAddress"] },
      "BillEmailCc" => { "Address" => emails.join(", ") },
      "InvoiceLink" => invoice["OnlineInvoiceUrl"].presence || invoice["InvoiceLink"],
      "Status" => invoice["Status"],
      "Type" => invoice["Type"]
    }
  end

  def self.to_books_customer(contact)
    {
      "Id" => contact["ContactID"].to_s,
      "DisplayName" => contact["Name"],
      "PrimaryEmailAddr" => { "Address" => contact["EmailAddress"] }
    }
  end

  def self.voided?(invoice)
    VOID_STATUSES.include?(invoice["Status"].to_s.upcase)
  end

  def self.sales_invoice?(invoice)
    invoice["Type"].to_s == "ACCREC"
  end

  def self.iso_date(value)
    parsed = parse_date(value)
    parsed&.iso8601
  end

  def self.parse_date(value)
    return if value.blank?

    str = value.to_s
    if (match = str.match(%r{/Date\((-?\d+)([+-]\d+)?\)/}))
      return Time.zone.at(match[1].to_i / 1000.0).to_date
    end

    Date.parse(str)
  rescue Date::Error
    nil
  end

  def self.contact_person_emails(contact)
    Array(contact["ContactPersons"]).filter_map do |person|
      email = person.is_a?(Hash) ? person["EmailAddress"].to_s.strip.downcase : ""
      email.presence
    end.uniq
  end
end
