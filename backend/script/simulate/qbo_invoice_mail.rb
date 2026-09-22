# frozen_string_literal: true

require "cgi"

module Simulate
  # Recreates the QBO invoice notification (plain + HTML). Script-only.
  class QboInvoiceMail
    def self.build(invoice:, company_name:, subject: nil)
      new(invoice: invoice, company_name: company_name, subject: subject).build
    end

    def initialize(invoice:, company_name:, subject: nil)
      @invoice = invoice
      @company_name = company_name.to_s.presence || "QuickBooks"
      @subject_override = subject.to_s.presence
    end

    def build
      {
        subject: @subject_override.presence || "Invoice #{doc_number} from #{company_name}",
        text: text_body,
        html: html_body,
        filename: "Invoice_#{doc_number}.pdf"
      }
    end

    private

    attr_reader :invoice, :company_name

    def customer_name
      invoice.dig("CustomerRef", "name").presence || "Customer"
    end

    def doc_number
      invoice["DocNumber"].presence || invoice["Id"].to_s
    end

    def txn_date
      format_date(invoice["TxnDate"])
    end

    def due_date
      format_date(invoice["DueDate"])
    end

    def amount_due
      raw = invoice["Balance"].presence || invoice["TotalAmt"]
      format("$%.2f", BigDecimal(raw.to_s))
    end

    def invoice_link
      invoice["InvoiceLink"].to_s.presence
    end

    def h(value)
      CGI.escapeHTML(value.to_s)
    end

    def format_date(value)
      return "" if value.blank?

      Date.parse(value.to_s).strftime("%m/%d/%Y")
    rescue Date::Error
      value.to_s
    end

    def text_body
      pay = invoice_link.present? ? "\n------------------------------ Pay online ----------------------------------\nView and pay this invoice: #{invoice_link}\n" : ""
      <<~TEXT
        Dear #{customer_name},

        Your invoice is attached. Please remit payment at your earliest convenience.
        Thank you for your business - we appreciate it very much.

        Sincerely,
        #{company_name}

        ------------------------   Invoice Summary  --------------------------
        Invoice # : #{doc_number}
        Invoice Date: #{txn_date}
        Due Date: #{due_date}
        Amount Due: #{amount_due}

        The complete version has been provided as an attachment to this email.
        ---------------------------------------------------------------------
        #{pay}
      TEXT
    end

    def html_body
      pay = if invoice_link.present?
        <<~HTML
          <div style="margin-top: 25px; text-align: center;">
            <a href="#{h(invoice_link)}"
               style="background-color: #2ca01c; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
              View and pay this invoice
            </a>
          </div>
        HTML
      else
        ""
      end

      <<~HTML
        <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #333333; max-width: 600px;">
          <p>Dear #{h(customer_name)},</p>
          <p>
            Your invoice is attached. Please remit payment at your earliest convenience.<br>
            Thank you for your business - we appreciate it very much.
          </p>
          <p>
            Sincerely,<br>
            <strong>#{h(company_name)}</strong>
          </p>
          <div style="border-top: 1px dashed #cccccc; border-bottom: 1px dashed #cccccc; padding: 12px 0; margin: 24px 0;">
            <div style="font-weight: bold; text-align: center; margin-bottom: 10px; color: #555555;">
              ------------------------ &nbsp;&nbsp; Invoice Summary &nbsp;&nbsp; --------------------------
            </div>
            <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
              <tr><td style="padding: 2px 0; width: 120px;"><strong>Invoice # :</strong></td><td>#{h(doc_number)}</td></tr>
              <tr><td style="padding: 2px 0;"><strong>Invoice Date:</strong></td><td>#{h(txn_date)}</td></tr>
              <tr><td style="padding: 2px 0;"><strong>Due Date:</strong></td><td>#{h(due_date)}</td></tr>
              <tr><td style="padding: 2px 0;"><strong>Amount Due:</strong></td><td>#{h(amount_due)}</td></tr>
            </table>
            <p style="margin-top: 12px; margin-bottom: 0; font-size: 12px; color: #666666;">
              The complete version has been provided as an attachment to this email.
            </p>
          </div>
          #{pay}
        </div>
      HTML
    end
  end
end
