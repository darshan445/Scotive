# frozen_string_literal: true

# Deterministic chase copy for cadence outbox rows. Invoice #, amount, due date, pay link.
module Cadence::Copy
  module_function

  def subject(invoice, conversation)
    existing = conversation&.subject.to_s.strip
    base = existing.presence || "Invoice #{invoice.invoice_number}"
    base.match?(/\ARe:\s/i) ? base : "Re: #{base}"
  end

  def body(invoice, step)
    lines = [ "Hi,", "", paragraph(invoice, step) ]
    pay = pay_line(invoice)
    lines += [ "", pay ] if pay.present?
    lines += [ "", "Thanks" ]
    lines.join("\n")
  end

  def paragraph(invoice, step)
    number = invoice.invoice_number
    amount = money(invoice, invoice.total_amount)
    due = format_date(invoice.due_date)
    remaining = money(invoice, invoice.balance_remaining)
    promise = format_date(invoice.active_promise_date)

    case step
    when "notice_minus_3"
      "Just a heads-up that invoice #{number} for #{amount} is due on #{due}."
    when "due_today"
      "Invoice #{number} for #{amount} is due today."
    when "nudge_plus_3"
      "Just checking in on invoice #{number} for #{amount}, due #{due}. Remaining balance is #{remaining}."
    when "firm_plus_7"
      "Following up on overdue invoice #{number} for #{amount} (due #{due}). Remaining balance is #{remaining}. Please let me know if you need anything to process this."
    when "urgent_plus_14"
      "Invoice #{number} for #{amount} is now #{days_late(invoice)} days past due (due #{due}). Remaining balance is #{remaining}. Please send payment or reply with an update."
    when "broken_promise"
      "You mentioned payment would be made by #{promise} for invoice #{number} (#{amount}). I have not seen it land yet. Can you confirm when it will go out?"
    else
      "Following up on invoice #{number} for #{amount}, due #{due}. Remaining balance is #{remaining}."
    end
  end

  def pay_line(invoice)
    token = invoice.pay_link_token.to_s.strip
    return if token.blank?

    token.match?(/\Ahttps?:\/\//i) ? "Pay here: #{token}" : "Payment reference: #{token}"
  end

  def money(invoice, amount)
    value = format("%.2f", amount.to_d)
    invoice.currency.to_s.upcase == "USD" ? "$#{value}" : "#{invoice.currency} #{value}"
  end

  def format_date(value)
    value&.to_date&.strftime("%B %-d, %Y")
  end

  def days_late(invoice)
    today = invoice.organization&.today || Date.current
    [ (today - invoice.due_date).to_i, 1 ].max
  end
end
