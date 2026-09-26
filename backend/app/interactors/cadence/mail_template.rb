# frozen_string_literal: true

require "cgi"

# QBO-style HTML/text wrapper. AI writes the letter. This adds spacing, invoice summary, and the pay button.
module Cadence::MailTemplate
  PAY_LABEL = "View and pay this invoice"
  module_function

  def for(invoice, prose:, include_pay_link: false)
    clean = Cadence::Copy.strip_pay_urls(prose.to_s, invoice)
    href = pay_href(invoice) if include_pay_link
    {
      html: html_body(invoice, clean, href),
      text: text_body(invoice, clean, href),
      preview: preview(invoice, include_pay_link: include_pay_link && href.present?)
    }
  end

  def preview(invoice, include_pay_link: false)
    href = pay_href(invoice) if include_pay_link
    {
      invoice_number: invoice.invoice_number,
      issue_date: Cadence::Copy.format_date(invoice.issue_date),
      due_date: Cadence::Copy.format_date(invoice.due_date),
      amount_due: Cadence::Copy.money(invoice, invoice.balance_remaining),
      include_pay_link: href.present?,
      pay_label: PAY_LABEL
    }
  end

  def pay_href(invoice)
    token = invoice.pay_link_token.to_s.strip
    token if token.match?(/\Ahttps?:\/\//i)
  end

  def html_body(invoice, prose, href)
    <<~HTML
      <div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.55; color: #222222; max-width: 600px;">
        #{prose_html(prose)}
        <div style="background: #f4f4f4; padding: 16px 18px; margin: 28px 0 8px;">
          <div style="font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: #666666; margin-bottom: 10px;">Invoice summary</div>
          <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
            <tr><td style="padding: 3px 0; width: 140px; color: #555555;">Invoice #</td><td>#{h(invoice.invoice_number)}</td></tr>
            <tr><td style="padding: 3px 0; color: #555555;">Invoice date</td><td>#{h(Cadence::Copy.format_date(invoice.issue_date))}</td></tr>
            <tr><td style="padding: 3px 0; color: #555555;">Due date</td><td>#{h(Cadence::Copy.format_date(invoice.due_date))}</td></tr>
            <tr><td style="padding: 3px 0; color: #555555;">Amount due</td><td>#{h(Cadence::Copy.money(invoice, invoice.balance_remaining))}</td></tr>
          </table>
        </div>
        #{pay_html(href)}
      </div>
    HTML
  end

  def text_body(invoice, prose, href)
    summary = <<~TEXT
      #{prose.to_s.strip}

      ------------------------   Invoice Summary  --------------------------
      Invoice # : #{invoice.invoice_number}
      Invoice Date: #{Cadence::Copy.format_date(invoice.issue_date)}
      Due Date: #{Cadence::Copy.format_date(invoice.due_date)}
      Amount Due: #{Cadence::Copy.money(invoice, invoice.balance_remaining)}
      ---------------------------------------------------------------------
    TEXT
    return summary if href.blank?

    "#{summary}\n------------------------------ Pay online ----------------------------------\n#{PAY_LABEL}: #{href}\n"
  end

  def prose_html(prose)
    blocks = prose.to_s.strip.split(/\n{2,}/)
    return "<p></p>" if blocks.empty?

    blocks.map { |block| "<p style=\"margin: 0 0 12px;\">#{h(block).gsub("\n", "<br>")}</p>" }.join("\n")
  end

  def pay_html(href)
    return "" if href.blank?

    <<~HTML
      <div style="margin-top: 20px;">
        <div style="font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: #666666; margin-bottom: 10px;">Pay online</div>
        <a href="#{h(href)}"
           style="background-color: #2ca01c; color: #ffffff; padding: 12px 22px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
          #{PAY_LABEL}
        </a>
      </div>
    HTML
  end

  def h(value)
    CGI.escapeHTML(value.to_s)
  end
end
